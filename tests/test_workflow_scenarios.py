from typing import Any, List
from unittest.mock import AsyncMock, MagicMock

import pytest
from coreason_identity.models import UserContext

from coreason_catalog.models import DataSensitivity, SourceManifest
from coreason_catalog.services.broker import FederationBroker, QueryDispatcher
from coreason_catalog.services.embedding import EmbeddingService
from coreason_catalog.services.policy_engine import PolicyEngine
from coreason_catalog.services.provenance import ProvenanceService
from coreason_catalog.services.vector_store import VectorStore


@pytest.fixture  # type: ignore[misc]
def broker_setup() -> tuple[FederationBroker, MagicMock, MagicMock, AsyncMock]:
    vector_store = MagicMock(spec=VectorStore)
    policy_engine = MagicMock(spec=PolicyEngine)
    embedding_service = MagicMock(spec=EmbeddingService)
    embedding_service.embed_text.return_value = [0.1] * 384
    dispatcher = AsyncMock(spec=QueryDispatcher)
    provenance_service = MagicMock(spec=ProvenanceService)
    provenance_service.generate_provenance.return_value = "sig"

    broker = FederationBroker(
        vector_store=vector_store,
        policy_engine=policy_engine,
        embedding_service=embedding_service,
        dispatcher=dispatcher,
        provenance_service=provenance_service,
    )
    return broker, vector_store, policy_engine, dispatcher


def create_source(urn: str, acls: List[str]) -> SourceManifest:
    return SourceManifest(
        urn=urn,
        name=f"Source {urn}",
        description="desc",
        endpoint_url="http://url",
        geo_location="US",
        sensitivity=DataSensitivity.INTERNAL,
        owner_group="owner",
        access_policy="allow { true }",
        acls=acls,
    )


@pytest.mark.asyncio  # type: ignore[misc]
async def test_workflow_access_upgrade(
    broker_setup: tuple[FederationBroker, MagicMock, MagicMock, AsyncMock],
) -> None:
    """
    Scenario: User context evolves.
    1. User has no groups -> Sees 0 items.
    2. User gains Group A -> Sees Item A.
    3. User gains Group B -> Sees Item A and Item B.
    """
    broker, vector_store, policy_engine, dispatcher = broker_setup

    # Mock Policy Engine to use real check_access logic but mock evaluate_policy
    # We can rely on the side_effect trick or just reimplement simple logic for the mock
    def check_access_impl(asset: SourceManifest, user_context: UserContext) -> bool:
        if user_context.claims.get("is_service_account"):
            return True
        return bool(set(asset.acls) & set(user_context.groups))

    policy_engine.check_access.side_effect = check_access_impl
    policy_engine.evaluate_policy.return_value = True  # OPA always says yes for this test

    # Data Setup
    source_a = create_source("urn:A", ["group:A"])
    source_b = create_source("urn:B", ["group:B"])
    # Search always returns both candidates
    vector_store.search.return_value = [source_a, source_b]

    dispatcher.dispatch.return_value = {"val": "data"}

    # Step 1: No groups
    ctx_none = UserContext(user_id="u1", email="u1@ex.com", groups=[])
    resp1 = await broker.dispatch_query("q", ctx_none)
    assert len(resp1.aggregated_results) == 0

    # Step 2: Group A
    ctx_a = UserContext(user_id="u1", email="u1@ex.com", groups=["group:A"])
    resp2 = await broker.dispatch_query("q", ctx_a)
    assert len(resp2.aggregated_results) == 1
    assert resp2.aggregated_results[0].source_urn == "urn:A"

    # Step 3: Group A and B
    ctx_ab = UserContext(user_id="u1", email="u1@ex.com", groups=["group:A", "group:B"])
    resp3 = await broker.dispatch_query("q", ctx_ab)
    assert len(resp3.aggregated_results) == 2
    # Verify both are present
    urns = sorted([r.source_urn for r in resp3.aggregated_results])
    assert urns == ["urn:A", "urn:B"]


@pytest.mark.asyncio  # type: ignore[misc]
async def test_workflow_mixed_governance(
    broker_setup: tuple[FederationBroker, MagicMock, MagicMock, AsyncMock],
) -> None:
    """
    Scenario:
    - Source 1: Blocked by ACL (User lacks group).
    - Source 2: Allowed by ACL, Blocked by OPA (Policy Logic).
    - Source 3: Allowed by both, Dispatch fails (Network).
    - Source 4: Allowed by both, Dispatch succeeds.
    """
    broker, vector_store, policy_engine, dispatcher = broker_setup

    s1 = create_source("urn:acl_block", ["group:super_secret"])
    s2 = create_source("urn:opa_block", ["group:common"])
    s3 = create_source("urn:net_fail", ["group:common"])
    s4 = create_source("urn:success", ["group:common"])

    vector_store.search.return_value = [s1, s2, s3, s4]

    # ACL Logic
    def check_access_impl(asset: SourceManifest, user_context: UserContext) -> bool:
        return bool(set(asset.acls) & set(user_context.groups))

    policy_engine.check_access.side_effect = check_access_impl

    # OPA Logic
    def evaluate_policy_impl(policy: str, input_data: dict[str, Any]) -> bool:
        # Block urn:opa_block
        obj_urn = input_data["object"]["urn"]
        if obj_urn == "urn:opa_block":
            return False
        return True

    policy_engine.evaluate_policy.side_effect = evaluate_policy_impl

    # Dispatch Logic
    async def dispatch_impl(source: SourceManifest, intent: str) -> Any:
        if source.urn == "urn:net_fail":
            raise RuntimeError("Network Error")
        return {"data": "ok"}

    dispatcher.dispatch.side_effect = dispatch_impl

    # User Context
    ctx = UserContext(user_id="u1", email="u1@ex.com", groups=["group:common"])

    # Execution
    resp = await broker.dispatch_query("q", ctx)

    # Assertions
    # s1 blocked by ACL -> Not in list
    # s2 blocked by OPA -> Not in list
    # s3 fail -> ERROR
    # s4 success -> SUCCESS
    # Total results: 2
    assert len(resp.aggregated_results) == 2

    results = {r.source_urn: r for r in resp.aggregated_results}

    assert "urn:acl_block" not in results
    assert "urn:opa_block" not in results

    assert results["urn:net_fail"].status == "ERROR"
    assert results["urn:success"].status == "SUCCESS"
    assert resp.partial_content is True
