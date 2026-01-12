# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_catalog

from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class DataSensitivity(str, Enum):
    """
    Data Sensitivity levels for classification and access control.
    """

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    PII = "PII"
    GxP_LOCKED = "GxP_LOCKED"


class SourceManifest(BaseModel):
    """
    Manifest definition for a registered MCP Source.
    Used for semantic indexing and governance.
    """

    urn: str = Field(..., description="Unique Resource Name of the source (e.g., urn:coreason:mcp:clin_data_01)")
    name: str = Field(..., description="Human-readable name of the source")
    description: str = Field(..., description="Natural language description used for semantic embedding")
    endpoint_url: str = Field(..., description="The connection URL (e.g., sse://...)")
    geo_location: str = Field(..., description="Physical location of the data (e.g., 'EU', 'US')")
    sensitivity: DataSensitivity = Field(..., description="Data sensitivity classification")
    owner_group: str = Field(..., description="The team or group that owns this source")
    access_policy: str = Field(..., description="OPA Rego policy string")


class SourceResult(BaseModel):
    """
    Result from a single MCP source.
    """

    source_urn: str
    status: Literal["SUCCESS", "ERROR", "BLOCKED_BY_POLICY", "PARTIAL_CONTENT"]
    data: Any = Field(default=None, description="The returned data payload (if any)")
    latency_ms: float = Field(..., description="Response latency in milliseconds")


class CatalogResponse(BaseModel):
    """
    Aggregated response from the Federation Broker.
    """

    query_id: UUID
    aggregated_results: list[SourceResult]
    provenance_signature: str = Field(..., description="W3C PROV-O JSON-LD signature")
