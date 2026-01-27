from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from coreason_identity.models import UserContext
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
    source_pointer: Optional[Dict[str, str]] = Field(None, description="Pointer to external data source")
    acls: List[str] = Field(default_factory=list, description="List of security group IDs for row-level security")

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
    partial_content: bool = False  # Warning flag for fail-safe aggregation


class QueryRequest(BaseModel):
    intent: str = Field(..., description="The natural language query intent")
    user_context: UserContext = Field(..., description="The user context for policy evaluation")
    limit: int = Field(10, description="Max number of sources to query")
