import json
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest

from coreason_catalog.api.routes import query_catalog
from coreason_catalog.models import DataSensitivity, QueryRequest, SourceManifest
from coreason_catalog.services.broker import FederationBroker
from coreason_catalog.services.policy_engine import PolicyEngine


class TestPolicyEngineACLs:
    def test_acls_empty_required(self) -> None:
        engine = PolicyEngine(opa_path="mock")
        # No ACLs required -> Access allowed
        assert engine.check_acls([], ["group:A"]) is True
        assert engine.check_acls([], []) is True

    def test_acls_match(self) -> None:
        engine = PolicyEngine(opa_path="mock")
        required = ["group:A", "group:B"]
        user_groups = ["group:A", "group:C"]
        assert engine.check_acls(required, user_groups) is True

    def test_acls_no_match(self) -> None:
        engine = PolicyEngine(opa_path="mock")
        required = ["group:A", "group:B"]
        user_groups = ["group:C", "group:D"]
        assert engine.check_acls(required, user_groups) is False

    def test_acls_empty_user_groups(self) -> None:
        engine = PolicyEngine(opa_path="mock")
        required = ["group:A"]
        assert engine.check_acls(required, []) is False


@pytest.mark.asyncio  # type: ignore[misc]
async def test_broker_acl_filtering() -> None:
    # Mock dependencies
    vector_store = MagicMock()

    # Use a pure mock for policy engine to avoid instantiation and mypy issues
    policy_engine = MagicMock(spec=PolicyEngine)

    # Implement a fake check_acls that replicates logic for the test
    def fake_check_acls(required_acls: List[str], user_groups: List[str]) -> bool:
        if not required_acls:
            return True
        return not set(required_acls).isdisjoint(user_groups)

    policy_engine.check_acls.side_effect = fake_check_acls
    policy_engine.evaluate_policy.return_value = True

    embedding_service = MagicMock()
    embedding_service.embed_text.return_value = [0.1] * 384  # Dimension? Assumed mocked

    dispatcher = MagicMock()
    # Mock dispatch return
    dispatcher.dispatch = AsyncMock(return_value={"some": "data"})

    provenance_service = MagicMock()
    provenance_service.generate_provenance.return_value = "sig"

    broker = FederationBroker(
        vector_store=vector_store,
        policy_engine=policy_engine,
        embedding_service=embedding_service,
        dispatcher=dispatcher,
        provenance_service=provenance_service,
    )

    # Setup candidates
    source_allowed = SourceManifest(
        urn="urn:allowed",
        name="Allowed",
        description="desc",
        endpoint_url="url",
        geo_location="EU",
        sensitivity=DataSensitivity.INTERNAL,
        owner_group="g1",
        access_policy="allow",
        acls=["group:users"],
    )
    source_blocked = SourceManifest(
        urn="urn:blocked",
        name="Blocked",
        description="desc",
        endpoint_url="url",
        geo_location="EU",
        sensitivity=DataSensitivity.INTERNAL,
        owner_group="g1",
        access_policy="allow",
        acls=["group:admins"],
    )

    vector_store.search.return_value = [source_allowed, source_blocked]

    # Dispatch query with user context having "group:users"
    user_context = {"groups": ["group:users"], "user_id": "u1"}
    response = await broker.dispatch_query("test query", user_context)

    # Verification
    # Should only dispatch to source_allowed
    assert len(response.aggregated_results) == 1
    assert response.aggregated_results[0].source_urn == "urn:allowed"

    # Test with malformed groups (not a list)
    user_context_bad_groups = {"groups": "not-a-list", "user_id": "u1"}
    response = await broker.dispatch_query("test query", user_context_bad_groups)
    # Should treat groups as [], so should block source_allowed (which requires "group:users")
    assert len(response.aggregated_results) == 0


@pytest.mark.asyncio  # type: ignore[misc]
async def test_api_context_propagation() -> None:
    # Mock broker
    mock_broker = AsyncMock()
    mock_broker.dispatch_query.return_value = MagicMock()

    request = QueryRequest(intent="test", user_context={"original": "context"}, limit=10)

    # Case 1: Header provided
    header_context = json.dumps({"groups": ["group:header"]})
    await query_catalog(request, x_user_context=header_context, broker=mock_broker)

    # Check that broker received the header context
    mock_broker.dispatch_query.assert_called_with("test", {"groups": ["group:header"]}, 10)

    # Case 2: Header not provided
    mock_broker.reset_mock()
    await query_catalog(request, x_user_context=None, broker=mock_broker)
    mock_broker.dispatch_query.assert_called_with("test", {"original": "context"}, 10)

    # Case 3: Invalid header (not JSON)
    mock_broker.reset_mock()
    await query_catalog(request, x_user_context="invalid-json", broker=mock_broker)
    mock_broker.dispatch_query.assert_called_with("test", {"original": "context"}, 10)

    # Case 4: Header valid JSON but not dict
    mock_broker.reset_mock()
    await query_catalog(request, x_user_context="[1, 2]", broker=mock_broker)
    mock_broker.dispatch_query.assert_called_with("test", {"original": "context"}, 10)
