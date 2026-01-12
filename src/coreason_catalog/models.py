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
    """
    Manifest definition for a registered MCP Source.
    Used for semantic indexing and governance.
    """

    model_config = ConfigDict(extra="forbid")

    urn: str = Field(..., description="Unique Resource Name of the source (e.g., urn:coreason:mcp:clin_data_01)")
    name: str = Field(..., description="Human-readable name of the source")
    description: str = Field(..., description="Natural language description used for semantic embedding")
    endpoint_url: str = Field(..., description="The connection URL (e.g., sse://...)")
    geo_location: str = Field(..., description="Physical location of the data (e.g., 'EU', 'US')")
    sensitivity: DataSensitivity = Field(..., description="Data sensitivity classification")
    owner_group: str = Field(..., description="The team or group that owns this source")
    access_policy: str = Field(..., description="OPA Rego policy string")

    @field_validator("urn")
    @classmethod
    def validate_urn(cls, v: str) -> str:
        if not v.startswith("urn:"):
            raise ValueError('URN must start with "urn:"')
        return v


class SourceResult(BaseModel):
    """
    Result from a single MCP source.
    """

    model_config = ConfigDict(extra="forbid")

    source_urn: str
    status: Literal["SUCCESS", "ERROR", "BLOCKED_BY_POLICY", "PARTIAL_CONTENT"]
    data: Any = Field(default=None, description="The returned data payload (if any)")
    latency_ms: float = Field(..., description="Response latency in milliseconds")

    @field_validator("latency_ms")
    @classmethod
    def validate_latency(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Latency cannot be negative")
        return v


class CatalogResponse(BaseModel):
    """
    Aggregated response from the Federation Broker.
    """

    model_config = ConfigDict(extra="forbid")

    query_id: UUID
    aggregated_results: list[SourceResult]
    provenance_signature: str = Field(..., description="W3C PROV-O JSON-LD signature")
