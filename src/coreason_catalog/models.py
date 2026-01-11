from enum import Enum
from typing import Any, List, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class DataSensitivity(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    PII = "PII"  # Personally Identifiable Information
    GxP_LOCKED = "GxP_LOCKED"


class SourceManifest(BaseModel):
    urn: str = Field(..., description="URN of the source, e.g. urn:coreason:mcp:clin_data_01")
    name: str = Field(..., description="Human readable name of the source")
    description: str = Field(..., description="Natural language description for semantic search")
    endpoint_url: str = Field(..., description="The endpoint URL, e.g. sse://10.0.0.5:8080")

    # Governance Metadata
    geo_location: str = Field(..., description="Geolocation tag, e.g. EU")
    sensitivity: DataSensitivity = Field(..., description="Sensitivity classification")
    owner_group: str = Field(..., description="Owner group identifier")

    # OPA Policy (Rego)
    access_policy: str = Field(..., description="Rego policy string")


class SourceResult(BaseModel):
    source_urn: str
    status: Literal["SUCCESS", "ERROR", "BLOCKED_BY_POLICY"]
    data: Any
    latency_ms: float


class CatalogResponse(BaseModel):
    query_id: UUID
    aggregated_results: List[SourceResult]
    provenance_signature: str  # W3C PROV signature
