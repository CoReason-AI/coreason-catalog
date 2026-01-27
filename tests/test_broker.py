from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from coreason_identity.models import UserContext

from coreason_catalog.models import (
    CatalogResponse,
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
    # Mock return of embed_text to be a list of floats
    service.embed_text.return_value = [0.1] * 384
    return service


@pytest.fixture  # type: ignore[misc]
def mock_dispatcher() -> AsyncMock:
    dispatcher = AsyncMock(spec=QueryDispatcher)
    return dispatcher


@pytest.fixture  # type: ignore[misc]
def mock_provenance_service() -> MagicMock:
    service = MagicMock(spec=ProvenanceService)
    service.generate_provenance.return_value = '{"@context": {}, "@graph": []}'
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
def sample_manifest_us() -> SourceManifest:
    return SourceManifest(
        urn="urn:coreason:mcp:us_data",
        name="US Data",
        description="US Data Description",
        endpoint_url="http://us.example.com",
        geo_location="US",
        sensitivity=DataSensitivity.PII,
        owner_group="US_Team",
        access_policy="allow { input.subject.location == 'US' }",
    )


@pytest.fixture  # type: ignore[misc]
def sample_manifest_eu() -> SourceManifest:
    return SourceManifest(
        urn="urn:coreason:mcp:eu_data",
        name="EU Data",
        description="EU Data Description",
        endpoint_url="http://eu.example.com",
        geo_location="EU",
        sensitivity=DataSensitivity.GxP_LOCKED,
        owner_group="EU_Team",
        access_policy="allow { input.subject.location == 'EU' }",
    )


@pytest.mark.asyncio  # type: ignore[misc]
async def test_semantic_routing_discovery(
    broker: FederationBroker,
    mock_vector_store: MagicMock,
    mock_policy_engine: MagicMock,
    mock_dispatcher: AsyncMock,
    sample_manifest_us: SourceManifest,
    sample_manifest_eu: SourceManifest,
) -> None:
    """
    Story A: Semantic Routing.
    Verify that broker finds candidates, checks policy, and aggregates results.
    """
    # Setup
    user_context = UserContext(user_id="u1", email="test@example.com", groups=["admin"])
    intent = "Find patient data"

    # Vector Search returns both US and EU sources
    mock_vector_store.search.return_value = [sample_manifest_us, sample_manifest_eu]

    # Policy Engine allows both (for this test case, assume user has global access)
    mock_policy_engine.evaluate_policy.return_value = True
    # Also mock check_access to return True
    mock_policy_engine.check_access.return_value = True

    # Dispatcher returns data
    mock_dispatcher.dispatch.side_effect = [
        {"id": 1, "val": "US"},
        {"id": 2, "val": "EU"},
    ]

    # Act
    response = await broker.dispatch_query(intent, user_context)

    # Assert
    assert isinstance(response, CatalogResponse)
    assert len(response.aggregated_results) == 2
    assert response.aggregated_results[0].status == "SUCCESS"
    assert response.aggregated_results[1].status == "SUCCESS"

    # Verify calls
    mock_vector_store.search.assert_called_once()
    assert mock_policy_engine.evaluate_policy.call_count == 2
    assert mock_dispatcher.dispatch.call_count == 2


@pytest.mark.asyncio  # type: ignore[misc]
async def test_gdpr_firewall(
    broker: FederationBroker,
    mock_vector_store: MagicMock,
    mock_policy_engine: MagicMock,
    mock_dispatcher: AsyncMock,
    sample_manifest_us: SourceManifest,
    sample_manifest_eu: SourceManifest,
) -> None:
    """
    Story B: GDPR Firewall.
    User is US. EU source should be blocked.
    """
    # Setup
    user_context = UserContext(user_id="u1", email="test@example.com", groups=[])
    intent = "Global data"

    mock_vector_store.search.return_value = [sample_manifest_us, sample_manifest_eu]

    # Policy:
    # Call 1 (US Source) -> Allow
    # Call 2 (EU Source) -> Deny
    mock_policy_engine.evaluate_policy.side_effect = [True, False]
    mock_policy_engine.check_access.return_value = True

    mock_dispatcher.dispatch.return_value = {"data": "ok"}

    # Act
    response = await broker.dispatch_query(intent, user_context)

    # Assert
    assert len(response.aggregated_results) == 1
    assert response.aggregated_results[0].source_urn == sample_manifest_us.urn

    # Dispatcher should only be called once (for the allowed source)
    mock_dispatcher.dispatch.assert_called_once()
    args, _ = mock_dispatcher.dispatch.call_args
    assert args[0].urn == sample_manifest_us.urn


@pytest.mark.asyncio  # type: ignore[misc]
async def test_fail_safe_aggregation(
    broker: FederationBroker,
    mock_vector_store: MagicMock,
    mock_policy_engine: MagicMock,
    mock_dispatcher: AsyncMock,
    sample_manifest_us: SourceManifest,
    sample_manifest_eu: SourceManifest,
) -> None:
    """
    Test Fail-Safe Aggregation.
    One source works, one fails (500 error / exception). Response should contain both statuses.
    """
    # Setup
    mock_vector_store.search.return_value = [sample_manifest_us, sample_manifest_eu]
    mock_policy_engine.evaluate_policy.return_value = True
    mock_policy_engine.check_access.return_value = True

    # Dispatcher: US works, EU fails
    async def side_effect(source: SourceManifest, intent: str) -> Any:
        if source.urn == sample_manifest_eu.urn:
            raise RuntimeError("Connection Timeout")
        return {"data": "US Data"}

    mock_dispatcher.dispatch.side_effect = side_effect

    # Act
    response = await broker.dispatch_query("query", UserContext(user_id="u1", email="test@example.com"))

    # Assert
    assert len(response.aggregated_results) == 2

    us_result = next(r for r in response.aggregated_results if r.source_urn == sample_manifest_us.urn)
    eu_result = next(r for r in response.aggregated_results if r.source_urn == sample_manifest_eu.urn)

    assert us_result.status == "SUCCESS"
    assert us_result.data == {"data": "US Data"}

    assert eu_result.status == "ERROR"
    assert "Connection Timeout" in str(eu_result.data)

    # Verify partial_content flag
    assert response.partial_content is True


@pytest.mark.asyncio  # type: ignore[misc]
async def test_no_results(broker: FederationBroker, mock_vector_store: MagicMock) -> None:
    """Test when no sources are found."""
    mock_vector_store.search.return_value = []

    response = await broker.dispatch_query("weird query", UserContext(user_id="u1", email="test@example.com"))

    assert len(response.aggregated_results) == 0


@pytest.mark.asyncio  # type: ignore[misc]
async def test_embedding_failure(broker: FederationBroker, mock_embedding_service: MagicMock) -> None:
    """Test handling of embedding service failure."""
    mock_embedding_service.embed_text.side_effect = Exception("Model down")

    response = await broker.dispatch_query("query", UserContext(user_id="u1", email="test@example.com"))

    assert len(response.aggregated_results) == 0
    assert "Embedding Failed" in response.provenance_signature


@pytest.mark.asyncio  # type: ignore[misc]
async def test_vector_search_failure(
    broker: FederationBroker,
    mock_vector_store: MagicMock,
    mock_embedding_service: MagicMock,
) -> None:
    """Test handling of vector search failure."""
    mock_embedding_service.embed_text.return_value = [0.1] * 384
    mock_vector_store.search.side_effect = Exception("DB Down")

    response = await broker.dispatch_query("query", UserContext(user_id="u1", email="test@example.com"))

    assert len(response.aggregated_results) == 0
    assert "Search Failed" in response.provenance_signature


@pytest.mark.asyncio  # type: ignore[misc]
async def test_policy_engine_failure(
    broker: FederationBroker,
    mock_vector_store: MagicMock,
    mock_policy_engine: MagicMock,
    sample_manifest_us: SourceManifest,
) -> None:
    """
    Test handling of policy engine failure.
    If policy engine raises an exception, the source should be skipped (Fail Closed).
    """
    mock_vector_store.search.return_value = [sample_manifest_us]
    mock_policy_engine.check_access.return_value = True
    mock_policy_engine.evaluate_policy.side_effect = Exception("OPA Down")

    response = await broker.dispatch_query("query", UserContext(user_id="u1", email="test@example.com"))

    assert len(response.aggregated_results) == 0


@pytest.mark.asyncio  # type: ignore[misc]
async def test_empty_intent(
    broker: FederationBroker,
    mock_embedding_service: MagicMock,
    mock_vector_store: MagicMock,
) -> None:
    """
    Test handling of an empty intent string.
    """
    # Mock embedding behavior for empty string (some models might return vector, others might fail)
    # Assuming it returns a valid vector or we mock it to do so
    mock_embedding_service.embed_text.return_value = [0.0] * 384
    mock_vector_store.search.return_value = []

    response = await broker.dispatch_query("", UserContext(user_id="u1", email="test@example.com"))

    assert isinstance(response, CatalogResponse)
    assert len(response.aggregated_results) == 0
    mock_embedding_service.embed_text.assert_called_with("")
    mock_vector_store.search.assert_called_once()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_complex_federation_scenario(
    broker: FederationBroker,
    mock_vector_store: MagicMock,
    mock_policy_engine: MagicMock,
    mock_dispatcher: AsyncMock,
    sample_manifest_us: SourceManifest,
    sample_manifest_eu: SourceManifest,
) -> None:
    """
    Complex Scenario:
    - 5 Candidates found.
    - Source 1 (US): Allowed, Success
    - Source 2 (EU): Blocked by Policy
    - Source 3 (Network Fail): Allowed, Fails during dispatch
    - Source 4 (Empty): Allowed, Returns empty result
    - Source 5 (Exception): Allowed, Dispatch raises unexpected error
    """
    # Create extra sources
    source_network_fail = sample_manifest_us.model_copy(update={"urn": "urn:coreason:mcp:fail_net"})
    source_empty = sample_manifest_us.model_copy(update={"urn": "urn:coreason:mcp:empty"})
    source_exception = sample_manifest_us.model_copy(update={"urn": "urn:coreason:mcp:except"})

    # 1. Search returns 5 candidates
    candidates = [
        sample_manifest_us,  # 1. Good
        sample_manifest_eu,  # 2. Blocked
        source_network_fail,  # 3. Network Fail
        source_empty,  # 4. Empty Data
        source_exception,  # 5. Exception
    ]
    mock_vector_store.search.return_value = candidates

    # 2. Policy: Block EU (index 1), Allow others
    mock_policy_engine.check_access.return_value = True

    def policy_side_effect(policy: str, input_data: dict[str, Any]) -> bool:
        obj = input_data.get("object", {})
        if obj.get("urn") == sample_manifest_eu.urn:
            return False
        return True

    mock_policy_engine.evaluate_policy.side_effect = policy_side_effect

    # 3. Dispatcher behavior
    async def dispatch_side_effect(source: SourceManifest, intent: str) -> Any:
        if source.urn == source_network_fail.urn:
            raise RuntimeError("Network Timeout")
        if source.urn == source_exception.urn:
            raise ValueError("Parser Error")
        if source.urn == source_empty.urn:
            return {}
        if source.urn == sample_manifest_us.urn:
            return {"data": "Valid Data"}
        return None

    mock_dispatcher.dispatch.side_effect = dispatch_side_effect

    # Act
    response = await broker.dispatch_query("complex query", UserContext(user_id="u1", email="test@example.com"))

    # Assert
    # Total candidates: 5
    # Blocked: 1 (EU) -> Not in results
    # Allowed: 4
    # Results expected: 4
    assert len(response.aggregated_results) == 4

    # Verify individual results
    results_map = {r.source_urn: r for r in response.aggregated_results}

    # 1. Good Source
    assert results_map[sample_manifest_us.urn].status == "SUCCESS"
    assert results_map[sample_manifest_us.urn].data == {"data": "Valid Data"}

    # 2. Blocked Source (Should NOT be present)
    assert sample_manifest_eu.urn not in results_map

    # 3. Network Fail
    assert results_map[source_network_fail.urn].status == "ERROR"
    assert "Network Timeout" in str(results_map[source_network_fail.urn].data)

    # 4. Empty Result
    assert results_map[source_empty.urn].status == "SUCCESS"
    assert results_map[source_empty.urn].data == {}

    # 5. Exception
    assert results_map[source_exception.urn].status == "ERROR"
    assert "Parser Error" in str(results_map[source_exception.urn].data)

    # Verify partial_content flag (since errors occurred)
    assert response.partial_content is True
