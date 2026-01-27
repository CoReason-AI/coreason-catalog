from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from coreason_identity.models import UserContext

from coreason_catalog.models import (
    DataSensitivity,
    SourceManifest,
)
from coreason_catalog.services.broker import FederationBroker, QueryDispatcher
from coreason_catalog.services.embedding import EmbeddingService
from coreason_catalog.services.policy_engine import PolicyEngine
from coreason_catalog.services.provenance import ProvenanceService
from coreason_catalog.services.vector_store import VectorStore


@pytest.fixture  # type: ignore[misc]
def mock_vector_store() -> MagicMock:
    return MagicMock(spec=VectorStore)


@pytest.fixture  # type: ignore[misc]
def mock_policy_engine() -> MagicMock:
    return MagicMock(spec=PolicyEngine)


@pytest.fixture  # type: ignore[misc]
def mock_embedding_service() -> MagicMock:
    service = MagicMock(spec=EmbeddingService)
    service.embed_text.return_value = [0.1] * 384
    return service


@pytest.fixture  # type: ignore[misc]
def mock_dispatcher() -> AsyncMock:
    return AsyncMock(spec=QueryDispatcher)


@pytest.fixture  # type: ignore[misc]
def mock_provenance_service() -> MagicMock:
    service = MagicMock(spec=ProvenanceService)
    service.generate_provenance.return_value = "sig_test"
    return service


@pytest.fixture  # type: ignore[misc]
def broker(
    mock_vector_store: MagicMock,
    mock_policy_engine: MagicMock,
    mock_embedding_service: MagicMock,
    mock_dispatcher: AsyncMock,
    mock_provenance_service: MagicMock,
) -> FederationBroker:
    return FederationBroker(
        vector_store=mock_vector_store,
        policy_engine=mock_policy_engine,
        embedding_service=mock_embedding_service,
        dispatcher=mock_dispatcher,
        provenance_service=mock_provenance_service,
    )


@pytest.fixture  # type: ignore[misc]
def base_manifest() -> SourceManifest:
    return SourceManifest(
        urn="urn:coreason:mcp:base",
        name="Base Source",
        description="Base Desc",
        endpoint_url="http://base",
        geo_location="US",
        sensitivity=DataSensitivity.PUBLIC,
        owner_group="Public",
        access_policy="allow { true }",
    )


@pytest.mark.asyncio  # type: ignore[misc]
async def test_all_sources_fail(
    broker: FederationBroker,
    mock_vector_store: MagicMock,
    mock_policy_engine: MagicMock,
    mock_dispatcher: AsyncMock,
    base_manifest: SourceManifest,
) -> None:
    """
    Edge Case: All allowed sources fail.
    Result should have all errors and partial_content=True.
    """
    s1 = base_manifest.model_copy(update={"urn": "urn:1"})
    s2 = base_manifest.model_copy(update={"urn": "urn:2"})
    mock_vector_store.search.return_value = [s1, s2]
    mock_policy_engine.evaluate_policy.return_value = True
    mock_policy_engine.check_access.return_value = True

    # Dispatcher always raises exception
    mock_dispatcher.dispatch.side_effect = Exception("Down")

    response = await broker.dispatch_query("query", UserContext(user_id="u1", email="test@example.com"))

    assert len(response.aggregated_results) == 2
    assert all(r.status == "ERROR" for r in response.aggregated_results)
    assert response.partial_content is True


@pytest.mark.asyncio  # type: ignore[misc]
async def test_mixed_blocked_and_success(
    broker: FederationBroker,
    mock_vector_store: MagicMock,
    mock_policy_engine: MagicMock,
    mock_dispatcher: AsyncMock,
    base_manifest: SourceManifest,
) -> None:
    """
    Edge Case: Some sources blocked by policy, others succeed.
    Since blocked sources are filtered out silently, result contains only success.
    partial_content should be False.
    """
    s_allowed = base_manifest.model_copy(update={"urn": "urn:allowed"})
    s_blocked = base_manifest.model_copy(update={"urn": "urn:blocked"})
    mock_vector_store.search.return_value = [s_allowed, s_blocked]

    # Policy Logic
    mock_policy_engine.check_access.return_value = True

    def policy_side_effect(policy: str, input_data: dict[str, Any]) -> bool:
        return bool(input_data["object"]["urn"] == "urn:allowed")

    mock_policy_engine.evaluate_policy.side_effect = policy_side_effect
    mock_dispatcher.dispatch.return_value = "data"

    response = await broker.dispatch_query("query", UserContext(user_id="u1", email="test@example.com"))

    assert len(response.aggregated_results) == 1
    assert response.aggregated_results[0].source_urn == "urn:allowed"
    assert response.partial_content is False


@pytest.mark.asyncio  # type: ignore[misc]
async def test_mixed_blocked_and_error(
    broker: FederationBroker,
    mock_vector_store: MagicMock,
    mock_policy_engine: MagicMock,
    mock_dispatcher: AsyncMock,
    base_manifest: SourceManifest,
) -> None:
    """
    Edge Case: Some sources blocked, remaining one fails.
    Result contains 1 ERROR. partial_content should be True.
    """
    s_allowed_fail = base_manifest.model_copy(update={"urn": "urn:allowed_fail"})
    s_blocked = base_manifest.model_copy(update={"urn": "urn:blocked"})
    mock_vector_store.search.return_value = [s_allowed_fail, s_blocked]

    def policy_side_effect(policy: str, input_data: dict[str, Any]) -> bool:
        return bool(input_data["object"]["urn"] == "urn:allowed_fail")

    mock_policy_engine.check_access.return_value = True
    mock_policy_engine.evaluate_policy.side_effect = policy_side_effect
    mock_dispatcher.dispatch.side_effect = Exception("Fail")

    response = await broker.dispatch_query("query", UserContext(user_id="u1", email="test@example.com"))

    assert len(response.aggregated_results) == 1
    assert response.aggregated_results[0].status == "ERROR"
    assert response.partial_content is True


@pytest.mark.asyncio  # type: ignore[misc]
async def test_large_scale_partial_failure(
    broker: FederationBroker,
    mock_vector_store: MagicMock,
    mock_policy_engine: MagicMock,
    mock_dispatcher: AsyncMock,
    base_manifest: SourceManifest,
) -> None:
    """
    Complex Scenario: 20 sources. 19 Success, 1 Fail.
    partial_content must be True.
    """
    count = 20
    candidates = [base_manifest.model_copy(update={"urn": f"urn:{i}"}) for i in range(count)]
    mock_vector_store.search.return_value = candidates
    mock_policy_engine.evaluate_policy.return_value = True
    mock_policy_engine.check_access.return_value = True

    # Dispatcher: Fail for urn:0, Success for others
    async def dispatch_side_effect(source: SourceManifest, intent: str) -> Any:
        if source.urn == "urn:0":
            raise RuntimeError("Fail")
        return "Success"

    mock_dispatcher.dispatch.side_effect = dispatch_side_effect

    response = await broker.dispatch_query("query", UserContext(user_id="u1", email="test@example.com"))

    assert len(response.aggregated_results) == 20

    # Count statuses
    errors = [r for r in response.aggregated_results if r.status == "ERROR"]
    successes = [r for r in response.aggregated_results if r.status == "SUCCESS"]

    assert len(errors) == 1
    assert len(successes) == 19
    assert response.partial_content is True
