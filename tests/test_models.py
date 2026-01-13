from uuid import uuid4

import pytest
from coreason_catalog.models import CatalogResponse, DataSensitivity, SourceManifest, SourceResult
from pydantic import ValidationError


def test_data_sensitivity_enum() -> None:
    assert DataSensitivity.PUBLIC == "PUBLIC"
    assert DataSensitivity.GxP_LOCKED == "GxP_LOCKED"


def test_source_manifest_valid() -> None:
    manifest = SourceManifest(
        urn="urn:coreason:mcp:test",
        name="Test Source",
        description="A test source",
        endpoint_url="sse://localhost:8000",
        geo_location="US",
        sensitivity=DataSensitivity.INTERNAL,
        owner_group="Testers",
        access_policy="allow { true }",
    )
    assert manifest.urn == "urn:coreason:mcp:test"
    assert manifest.sensitivity == DataSensitivity.INTERNAL


def test_source_manifest_invalid_sensitivity() -> None:
    with pytest.raises(ValidationError):
        SourceManifest(
            urn="urn:coreason:mcp:test",
            name="Test Source",
            description="A test source",
            endpoint_url="sse://localhost:8000",
            geo_location="US",
            sensitivity="INVALID_LEVEL",
            owner_group="Testers",
            access_policy="allow { true }",
        )


def test_catalog_response_valid() -> None:
    result = SourceResult(source_urn="urn:coreason:mcp:test", status="SUCCESS", data={"foo": "bar"}, latency_ms=10.5)
    response = CatalogResponse(query_id=uuid4(), aggregated_results=[result], provenance_signature="sig_123")
    assert response.aggregated_results[0].status == "SUCCESS"
    assert response.provenance_signature == "sig_123"
