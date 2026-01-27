from typing import Generator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from coreason_catalog.dependencies import get_federation_broker, get_registry_service
from coreason_catalog.main import app
from coreason_catalog.models import CatalogResponse, SourceManifest, SourceResult


@pytest.fixture  # type: ignore[misc]
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture  # type: ignore[misc]
def mock_registry_service() -> MagicMock:
    mock = MagicMock()
    mock.register_source.return_value = None
    return mock


@pytest.fixture  # type: ignore[misc]
def mock_broker() -> AsyncMock:
    mock = AsyncMock()
    # Default behavior: successful empty response
    mock.dispatch_query.return_value = CatalogResponse(
        query_id=uuid4(), aggregated_results=[], provenance_signature="sig"
    )
    return mock


@pytest.fixture(autouse=True)  # type: ignore[misc]
def override_dependencies(mock_registry_service: MagicMock, mock_broker: AsyncMock) -> Generator[None, None, None]:
    app.dependency_overrides[get_registry_service] = lambda: mock_registry_service
    app.dependency_overrides[get_federation_broker] = lambda: mock_broker
    yield
    app.dependency_overrides = {}


def test_health_check(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_register_source_success(client: TestClient, mock_registry_service: MagicMock) -> None:
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

    response = client.post("/v1/sources", json=payload)

    assert response.status_code == 201
    assert response.json() == {"status": "registered", "urn": payload["urn"]}

    mock_registry_service.register_source.assert_called_once()
    call_args = mock_registry_service.register_source.call_args[0][0]
    assert isinstance(call_args, SourceManifest)
    assert call_args.urn == payload["urn"]


def test_register_source_validation_error(client: TestClient) -> None:
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


def test_register_source_value_error(client: TestClient, mock_registry_service: MagicMock) -> None:
    mock_registry_service.register_source.side_effect = ValueError("Embedding failed")

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

    response = client.post("/v1/sources", json=payload)
    assert response.status_code == 500
    assert "Embedding failed" in response.json()["detail"]


def test_register_source_runtime_error(client: TestClient, mock_registry_service: MagicMock) -> None:
    mock_registry_service.register_source.side_effect = RuntimeError("DB error")

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

    response = client.post("/v1/sources", json=payload)
    assert response.status_code == 500
    assert "DB error" in response.json()["detail"]


def test_register_source_unexpected_error(client: TestClient, mock_registry_service: MagicMock) -> None:
    mock_registry_service.register_source.side_effect = Exception("Unknown")

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

    response = client.post("/v1/sources", json=payload)
    assert response.status_code == 500
    assert "Internal Server Error" in response.json()["detail"]


def test_register_source_invalid_enum(client: TestClient) -> None:
    payload = {
        "urn": "urn:coreason:mcp:test_source",
        "name": "Test Source",
        "description": "A test source description",
        "endpoint_url": "sse://localhost:8080",
        "geo_location": "US",
        "sensitivity": "TOP_SECRET",
        "owner_group": "Test Group",
        "access_policy": "allow { input.subject.location == 'US' }",
    }
    response = client.post("/v1/sources", json=payload)
    assert response.status_code == 422


def test_register_source_idempotency(client: TestClient, mock_registry_service: MagicMock) -> None:
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

    client.post("/v1/sources", json=payload)
    client.post("/v1/sources", json=payload)

    assert mock_registry_service.register_source.call_count == 2


def test_register_source_dependency_failure(client: TestClient) -> None:
    # Explicitly break dependency for this test
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

    # Safe client for 500 check
    safe_client = TestClient(app, raise_server_exceptions=False)
    response = safe_client.post("/v1/sources", json=payload)
    assert response.status_code == 500


def test_register_source_large_payload(client: TestClient, mock_registry_service: MagicMock) -> None:
    large_description = "A" * 10000

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

    response = client.post("/v1/sources", json=payload)
    assert response.status_code == 201

    call_args = mock_registry_service.register_source.call_args[0][0]
    assert len(call_args.description) == 10000


def test_query_catalog_success(client: TestClient, mock_broker: AsyncMock) -> None:
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

    payload = {
        "intent": "Find data",
        "user_context": {"user_id": "u1", "role": "admin"},
        "limit": 5,
    }

    response = client.post("/v1/query", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["query_id"] == str(expected_response.query_id)
    assert len(data["aggregated_results"]) == 1
    mock_broker.dispatch_query.assert_called_once_with("Find data", {"user_id": "u1", "role": "admin"}, 5)


def test_query_catalog_validation_error(client: TestClient) -> None:
    payload = {
        "user_context": {"role": "admin"},
        "limit": 5,
    }
    response = client.post("/v1/query", json=payload)
    assert response.status_code == 422


def test_query_catalog_internal_error(client: TestClient, mock_broker: AsyncMock) -> None:
    mock_broker.dispatch_query.side_effect = Exception("Broker Failure")

    payload = {
        "intent": "Find data",
        "user_context": {},
    }

    safe_client = TestClient(app, raise_server_exceptions=False)
    response = safe_client.post("/v1/query", json=payload)
    assert response.status_code == 500
    assert "Internal Server Error" in response.json()["detail"]


def test_query_catalog_partial_content_true(client: TestClient, mock_broker: AsyncMock) -> None:
    mock_broker.dispatch_query.return_value = CatalogResponse(
        query_id=uuid4(), aggregated_results=[], provenance_signature="sig", partial_content=True
    )

    payload = {"intent": "test", "user_context": {}}
    response = client.post("/v1/query", json=payload)
    assert response.status_code == 200
    assert response.json()["partial_content"] is True


def test_query_catalog_empty_results(client: TestClient, mock_broker: AsyncMock) -> None:
    # Fixture sets empty results by default, but explicit is good for readability
    mock_broker.dispatch_query.return_value = CatalogResponse(
        query_id=uuid4(), aggregated_results=[], provenance_signature="sig"
    )

    payload = {"intent": "test", "user_context": {}}
    response = client.post("/v1/query", json=payload)
    assert response.status_code == 200
    assert response.json()["aggregated_results"] == []


def test_query_catalog_limit_zero(client: TestClient, mock_broker: AsyncMock) -> None:
    payload = {"intent": "test", "user_context": {}, "limit": 0}
    response = client.post("/v1/query", json=payload)
    assert response.status_code == 200
    mock_broker.dispatch_query.assert_called_once_with("test", {}, 0)


def test_query_catalog_complex_context(client: TestClient, mock_broker: AsyncMock) -> None:
    complex_context = {
        "user": {"id": "u1", "roles": ["admin", "researcher"]},
        "project": {"code": "P1", "flags": {"gxp": True}},
        "session": {"tokens": [1, 2, 3]},
    }
    payload = {"intent": "test", "user_context": complex_context}

    response = client.post("/v1/query", json=payload)
    assert response.status_code == 200
    call_args = mock_broker.dispatch_query.call_args
    assert call_args[0][1] == complex_context
