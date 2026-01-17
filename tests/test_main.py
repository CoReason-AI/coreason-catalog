from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from coreason_catalog.dependencies import get_federation_broker, get_registry_service
from coreason_catalog.main import app
from coreason_catalog.models import CatalogResponse, SourceManifest, SourceResult
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_register_source_success() -> None:
    # Setup
    mock_registry_service = MagicMock()
    mock_registry_service.register_source.return_value = None

    # Override dependency
    app.dependency_overrides[get_registry_service] = lambda: mock_registry_service

    payload = {
        "urn": "urn:coreason:mcp:test_source",
        "name": "Test Source",
        "description": "A test source description",
        "endpoint_url": "sse://localhost:8080",
        "geo_location": "US",
        "sensitivity": "PUBLIC",
        "owner_group": "Test Group",
        "access_policy": "allow { input.subject.location == 'US' }",
    }

    try:
        # Act
        response = client.post("/v1/sources", json=payload)

        # Assert
        assert response.status_code == 201
        assert response.json() == {"status": "registered", "urn": payload["urn"]}

        mock_registry_service.register_source.assert_called_once()
        call_args = mock_registry_service.register_source.call_args[0][0]
        assert isinstance(call_args, SourceManifest)
        assert call_args.urn == payload["urn"]
    finally:
        app.dependency_overrides = {}


def test_register_source_validation_error() -> None:
    # Missing required field 'urn'
    payload = {
        "name": "Test Source",
        "description": "A test source description",
        "endpoint_url": "sse://localhost:8080",
        "geo_location": "US",
        "sensitivity": "PUBLIC",
        "owner_group": "Test Group",
        "access_policy": "allow { input.subject.location == 'US' }",
    }

    response = client.post("/v1/sources", json=payload)

    assert response.status_code == 422


def test_register_source_value_error() -> None:
    # Setup
    mock_registry_service = MagicMock()
    mock_registry_service.register_source.side_effect = ValueError("Embedding failed")

    # Override dependency
    app.dependency_overrides[get_registry_service] = lambda: mock_registry_service

    payload = {
        "urn": "urn:coreason:mcp:error_source",
        "name": "Error Source",
        "description": "A test source description",
        "endpoint_url": "sse://localhost:8080",
        "geo_location": "US",
        "sensitivity": "PUBLIC",
        "owner_group": "Test Group",
        "access_policy": "allow { input.subject.location == 'US' }",
    }

    try:
        # Act
        response = client.post("/v1/sources", json=payload)

        # Assert
        assert response.status_code == 500
        assert "Embedding failed" in response.json()["detail"]
    finally:
        app.dependency_overrides = {}


def test_register_source_runtime_error() -> None:
    # Setup
    mock_registry_service = MagicMock()
    mock_registry_service.register_source.side_effect = RuntimeError("DB error")

    # Override dependency
    app.dependency_overrides[get_registry_service] = lambda: mock_registry_service

    payload = {
        "urn": "urn:coreason:mcp:error_source",
        "name": "Error Source",
        "description": "A test source description",
        "endpoint_url": "sse://localhost:8080",
        "geo_location": "US",
        "sensitivity": "PUBLIC",
        "owner_group": "Test Group",
        "access_policy": "allow { input.subject.location == 'US' }",
    }

    try:
        # Act
        response = client.post("/v1/sources", json=payload)

        # Assert
        assert response.status_code == 500
        assert "DB error" in response.json()["detail"]
    finally:
        app.dependency_overrides = {}


def test_register_source_unexpected_error() -> None:
    # Setup
    mock_registry_service = MagicMock()
    mock_registry_service.register_source.side_effect = Exception("Unknown")

    # Override dependency
    app.dependency_overrides[get_registry_service] = lambda: mock_registry_service

    payload = {
        "urn": "urn:coreason:mcp:error_source",
        "name": "Error Source",
        "description": "A test source description",
        "endpoint_url": "sse://localhost:8080",
        "geo_location": "US",
        "sensitivity": "PUBLIC",
        "owner_group": "Test Group",
        "access_policy": "allow { input.subject.location == 'US' }",
    }

    try:
        # Act
        response = client.post("/v1/sources", json=payload)

        # Assert
        assert response.status_code == 500
        assert "Internal Server Error" in response.json()["detail"]
    finally:
        app.dependency_overrides = {}


def test_register_source_invalid_enum() -> None:
    """Test that providing an invalid enum value returns a validation error (422)."""
    payload = {
        "urn": "urn:coreason:mcp:test_source",
        "name": "Test Source",
        "description": "A test source description",
        "endpoint_url": "sse://localhost:8080",
        "geo_location": "US",
        "sensitivity": "TOP_SECRET",  # Invalid enum
        "owner_group": "Test Group",
        "access_policy": "allow { input.subject.location == 'US' }",
    }

    response = client.post("/v1/sources", json=payload)

    assert response.status_code == 422
    assert "Input should be 'PUBLIC', 'INTERNAL', 'PII' or 'GxP_LOCKED'" in str(response.json())


def test_register_source_idempotency() -> None:
    """Test that registering the same source twice works (idempotency)."""
    # Setup
    mock_registry_service = MagicMock()
    mock_registry_service.register_source.return_value = None

    # Override dependency
    app.dependency_overrides[get_registry_service] = lambda: mock_registry_service

    payload = {
        "urn": "urn:coreason:mcp:test_source",
        "name": "Test Source",
        "description": "A test source description",
        "endpoint_url": "sse://localhost:8080",
        "geo_location": "US",
        "sensitivity": "PUBLIC",
        "owner_group": "Test Group",
        "access_policy": "allow { input.subject.location == 'US' }",
    }

    try:
        # First call
        response1 = client.post("/v1/sources", json=payload)
        assert response1.status_code == 201

        # Second call
        response2 = client.post("/v1/sources", json=payload)
        assert response2.status_code == 201

        # Assert service called twice
        assert mock_registry_service.register_source.call_count == 2
    finally:
        app.dependency_overrides = {}


def test_register_source_dependency_failure() -> None:
    """Test behavior when the dependency itself fails to initialize."""

    # Mock the dependency provider to raise an exception
    def broken_dependency() -> None:
        raise RuntimeError("Database connection failed")

    app.dependency_overrides[get_registry_service] = broken_dependency

    payload = {
        "urn": "urn:coreason:mcp:test_source",
        "name": "Test Source",
        "description": "A test source description",
        "endpoint_url": "sse://localhost:8080",
        "geo_location": "US",
        "sensitivity": "PUBLIC",
        "owner_group": "Test Group",
        "access_policy": "allow { input.subject.location == 'US' }",
    }

    # Use a client that doesn't raise server exceptions so we can check the 500 status
    safe_client = TestClient(app, raise_server_exceptions=False)

    try:
        response = safe_client.post("/v1/sources", json=payload)
        # FastAPI handles dependency errors by returning 500
        assert response.status_code == 500
    finally:
        app.dependency_overrides = {}


def test_register_source_large_payload() -> None:
    """Stress test with a large description."""
    # Setup
    mock_registry_service = MagicMock()
    mock_registry_service.register_source.return_value = None
    app.dependency_overrides[get_registry_service] = lambda: mock_registry_service

    large_description = "A" * 10000  # 10KB string

    payload = {
        "urn": "urn:coreason:mcp:test_source",
        "name": "Test Source",
        "description": large_description,
        "endpoint_url": "sse://localhost:8080",
        "geo_location": "US",
        "sensitivity": "PUBLIC",
        "owner_group": "Test Group",
        "access_policy": "allow { input.subject.location == 'US' }",
    }

    try:
        response = client.post("/v1/sources", json=payload)
        assert response.status_code == 201

        # Verify passed to service correctly
        mock_registry_service.register_source.assert_called_once()
        call_args = mock_registry_service.register_source.call_args[0][0]
        assert len(call_args.description) == 10000
    finally:
        app.dependency_overrides = {}


def test_query_catalog_success() -> None:
    # Setup
    mock_broker = AsyncMock()

    expected_response = CatalogResponse(
        query_id=uuid4(),
        aggregated_results=[
            SourceResult(
                source_urn="urn:test",
                status="SUCCESS",
                data={"foo": "bar"},
                latency_ms=10.0,
            )
        ],
        provenance_signature="signed_provenance",
    )
    mock_broker.dispatch_query.return_value = expected_response

    app.dependency_overrides[get_federation_broker] = lambda: mock_broker

    payload = {
        "intent": "Find data",
        "user_context": {"user_id": "u1", "role": "admin"},
        "limit": 5,
    }

    try:
        response = client.post("/v1/query", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["query_id"] == str(expected_response.query_id)
        assert len(data["aggregated_results"]) == 1
        assert data["aggregated_results"][0]["data"] == {"foo": "bar"}

        mock_broker.dispatch_query.assert_called_once_with("Find data", {"user_id": "u1", "role": "admin"}, 5)
    finally:
        app.dependency_overrides = {}


def test_query_catalog_validation_error() -> None:
    # Missing intent
    payload = {
        "user_context": {"role": "admin"},
        "limit": 5,
    }

    response = client.post("/v1/query", json=payload)
    assert response.status_code == 422


def test_query_catalog_internal_error() -> None:
    # Setup
    mock_broker = AsyncMock()
    mock_broker.dispatch_query.side_effect = Exception("Broker Failure")

    app.dependency_overrides[get_federation_broker] = lambda: mock_broker

    payload = {
        "intent": "Find data",
        "user_context": {},
    }

    # Use safe client
    safe_client = TestClient(app, raise_server_exceptions=False)

    try:
        response = safe_client.post("/v1/query", json=payload)
        assert response.status_code == 500
        assert "Internal Server Error" in response.json()["detail"]
    finally:
        app.dependency_overrides = {}
