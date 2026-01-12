# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_catalog

import uuid

import pytest
from pydantic import ValidationError

from coreason_catalog.models import (
    CatalogResponse,
    DataSensitivity,
    SourceManifest,
    SourceResult,
)


def test_data_sensitivity_enum() -> None:
    """Test DataSensitivity Enum values."""
    assert DataSensitivity.PUBLIC.value == "PUBLIC"
    assert DataSensitivity.INTERNAL.value == "INTERNAL"
    assert DataSensitivity.PII.value == "PII"
    assert DataSensitivity.GxP_LOCKED.value == "GxP_LOCKED"


def test_source_manifest_valid() -> None:
    """Test creating a valid SourceManifest."""
    manifest = SourceManifest(
        urn="urn:coreason:mcp:test_01",
        name="Test Source",
        description="A test source for unit testing.",
        endpoint_url="sse://localhost:8080",
        geo_location="US",
        sensitivity=DataSensitivity.INTERNAL,
        owner_group="Test_Team",
        access_policy="allow { true }",
    )
    assert manifest.urn == "urn:coreason:mcp:test_01"
    assert manifest.sensitivity == DataSensitivity.INTERNAL
    assert manifest.access_policy == "allow { true }"


def test_source_manifest_invalid_sensitivity() -> None:
    """Test SourceManifest validation with invalid sensitivity."""
    with pytest.raises(ValidationError) as excinfo:
        SourceManifest(
            urn="urn:coreason:mcp:test_02",
            name="Invalid Source",
            description="Invalid sensitivity.",
            endpoint_url="sse://localhost:8080",
            geo_location="EU",
            sensitivity="INVALID_LEVEL",  # type: ignore[arg-type]
            owner_group="Test_Team",
            access_policy="allow { true }",
        )
    assert "Input should be 'PUBLIC', 'INTERNAL', 'PII' or 'GxP_LOCKED'" in str(excinfo.value)


def test_source_manifest_missing_field() -> None:
    """Test SourceManifest validation with missing required field."""
    with pytest.raises(ValidationError) as excinfo:
        SourceManifest(  # type: ignore[call-arg]
            urn="urn:coreason:mcp:test_03",
            name="Missing Field Source",
            # description is missing
            endpoint_url="sse://localhost:8080",
            geo_location="US",
            sensitivity=DataSensitivity.PUBLIC,
            owner_group="Test_Team",
            access_policy="allow { true }",
        )
    assert "description" in str(excinfo.value)
    assert "Field required" in str(excinfo.value)


def test_source_result_valid() -> None:
    """Test creating a valid SourceResult."""
    result = SourceResult(
        source_urn="urn:coreason:mcp:test_01",
        status="SUCCESS",
        data={"key": "value"},
        latency_ms=123.45,
    )
    assert result.status == "SUCCESS"
    assert result.data == {"key": "value"}
    assert result.latency_ms == 123.45


def test_source_result_invalid_status() -> None:
    """Test SourceResult with invalid status."""
    with pytest.raises(ValidationError) as excinfo:
        SourceResult(
            source_urn="urn:coreason:mcp:test_01",
            status="UNKNOWN_STATUS",  # type: ignore[arg-type]
            latency_ms=10.0,
        )
    assert "Input should be 'SUCCESS', 'ERROR', 'BLOCKED_BY_POLICY' or 'PARTIAL_CONTENT'" in str(excinfo.value)


def test_catalog_response_valid() -> None:
    """Test creating a valid CatalogResponse."""
    query_id = uuid.uuid4()
    results = [
        SourceResult(
            source_urn="urn:coreason:mcp:src1",
            status="SUCCESS",
            data={"foo": "bar"},
            latency_ms=50.0,
        ),
        SourceResult(
            source_urn="urn:coreason:mcp:src2",
            status="BLOCKED_BY_POLICY",
            latency_ms=10.0,
        ),
    ]
    response = CatalogResponse(
        query_id=query_id,
        aggregated_results=results,
        provenance_signature="signed_hash_123",
    )
    assert response.query_id == query_id
    assert len(response.aggregated_results) == 2
    assert response.aggregated_results[1].status == "BLOCKED_BY_POLICY"


def test_model_serialization() -> None:
    """Test JSON serialization of models."""
    manifest = SourceManifest(
        urn="urn:coreason:mcp:test_01",
        name="Test",
        description="Desc",
        endpoint_url="url",
        geo_location="US",
        sensitivity=DataSensitivity.PII,
        owner_group="Owner",
        access_policy="policy",
    )
    json_str = manifest.model_dump_json()
    assert "urn:coreason:mcp:test_01" in json_str
    assert "PII" in json_str
