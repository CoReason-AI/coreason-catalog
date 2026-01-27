from unittest.mock import AsyncMock, MagicMock

import pytest
from coreason_identity.models import UserContext

from coreason_catalog.api.routes import query_catalog
from coreason_catalog.models import DataSensitivity, QueryRequest, SourceManifest
from coreason_catalog.services.broker import FederationBroker
from coreason_catalog.services.policy_engine import PolicyEngine


class TestPolicyEngineACLs:
    def test_access_service_account(self) -> None:
        engine = PolicyEngine(opa_path="mock")
        user_context = UserContext(user_id="sa", email="sa@bot.com", claims={"is_service_account": True})
        asset = SourceManifest(
            urn="urn:1",
            name="n",
            description="d",
            endpoint_url="url",
            geo_location="loc",
            sensitivity=DataSensitivity.PUBLIC,
            owner_group="og",
            access_policy="pol",
            acls=["group:A"],
        )
        assert engine.check_access(asset, user_context) is True

    def test_access_match(self) -> None:
        engine = PolicyEngine(opa_path="mock")
        user_context = UserContext(user_id="u1", email="u1@example.com", groups=["group:A"])
        asset = SourceManifest(
            urn="urn:1",
            name="n",
            description="d",
            endpoint_url="url",
            geo_location="loc",
            sensitivity=DataSensitivity.PUBLIC,
            owner_group="og",
            access_policy="pol",
            acls=["group:A", "group:B"],
        )
        assert engine.check_access(asset, user_context) is True

    def test_access_no_match(self) -> None:
        engine = PolicyEngine(opa_path="mock")
        user_context = UserContext(user_id="u1", email="u1@example.com", groups=["group:C"])
        asset = SourceManifest(
            urn="urn:1",
            name="n",
            description="d",
            endpoint_url="url",
            geo_location="loc",
            sensitivity=DataSensitivity.PUBLIC,
            owner_group="og",
            access_policy="pol",
            acls=["group:A", "group:B"],
        )
        assert engine.check_access(asset, user_context) is False


@pytest.mark.asyncio  # type: ignore[misc]
async def test_broker_acl_filtering() -> None:
    # Mock dependencies
    vector_store = MagicMock()

    # Use a pure mock for policy engine to avoid instantiation and mypy issues
    policy_engine = MagicMock(spec=PolicyEngine)

    # Implement a fake check_access that replicates logic for the test
    def fake_check_access(asset: SourceManifest, user_context: UserContext) -> bool:
        if user_context.claims.get("is_service_account") is True:
            return True
        return bool(set(asset.acls) & set(user_context.groups))

    policy_engine.check_access.side_effect = fake_check_access
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
    user_context = UserContext(groups=["group:users"], user_id="u1", email="u1@test.com")
    response = await broker.dispatch_query("test query", user_context)

    # Verification
    # Should only dispatch to source_allowed
    assert len(response.aggregated_results) == 1
    assert response.aggregated_results[0].source_urn == "urn:allowed"

    # Test with no groups
    user_context_no_groups = UserContext(groups=[], user_id="u1", email="u1@test.com")
    response = await broker.dispatch_query("test query", user_context_no_groups)
    # Should block source_allowed (which requires "group:users")
    assert len(response.aggregated_results) == 0


@pytest.mark.asyncio  # type: ignore[misc]
async def test_api_context_propagation() -> None:
    # Mock broker
    mock_broker = AsyncMock()
    mock_broker.dispatch_query.return_value = MagicMock()

    base_context = UserContext(user_id="u1", email="base@test.com", groups=["base"])
    request = QueryRequest(intent="test", user_context=base_context, limit=10)

    # Case 1: Header provided (valid UserContext)
    header_context_obj = UserContext(user_id="u2", email="header@test.com", groups=["header"])
    header_context = header_context_obj.model_dump_json()
    await query_catalog(request, x_user_context=header_context, broker=mock_broker)

    # Check that broker received the header context
    call_args = mock_broker.dispatch_query.call_args
    assert call_args[0][0] == "test"
    assert isinstance(call_args[0][1], UserContext)
    assert call_args[0][1].user_id == "u2"

    # Case 2: Header not provided
    mock_broker.reset_mock()
    await query_catalog(request, x_user_context=None, broker=mock_broker)
    call_args = mock_broker.dispatch_query.call_args
    assert isinstance(call_args[0][1], UserContext)
    assert call_args[0][1].user_id == "u1"

    # Case 3: Invalid header (not JSON)
    mock_broker.reset_mock()
    await query_catalog(request, x_user_context="invalid-json", broker=mock_broker)
    call_args = mock_broker.dispatch_query.call_args
    assert isinstance(call_args[0][1], UserContext)
    assert call_args[0][1].user_id == "u1"
