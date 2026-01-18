# Product Requirements Document: coreason-catalog

**Domain:** Semantic Data Discovery, Federated Governance, & Data Sovereignty
**Architectural Role:** The "Cartographer" / The Active Gateway
**Core Philosophy:** "The Map controls the Territory. Route by Meaning, Filter by Policy."
**Dependencies:** coreason-mcp (Targets), coreason-identity (Context), lancedb (Hybrid Search), open-policy-agent (Governance)

## 1. Executive Summary

coreason-catalog is the **Dynamic Registry and Routing Plane** for the CoReason ecosystem.

In a modern Bio-Pharma Data Mesh, data is decentralized. Clinical sites, labs, and third-party vendors host their own **MCP Data Servers**. The Reasoning Engine (coreason-cortex) cannot be expected to know the IP addresses, schema details, or sovereignty rules for hundreds of disparate sources.

coreason-catalog acts as a **Smart Proxy**. It provides a single "Virtual Database" interface to the Agent. Behind the scenes, it performs **Semantic Discovery** (mapping high-level intent to specific data sources) and **Sovereignty Enforcement** (ensuring a US Agent never queries an EU Server restricted by GDPR) before a single packet is sent.

## 2. Functional Philosophy

The agent must implement the **Register-Discover-Govern-Stamp Loop**:

1.  **Semantic Registration (SOTA):** Sources do not just register a name ("ClinDB_v2"). They register **Embeddings** of their schema and documentation. This allows the Catalog to route queries based on *meaning* ("Find Toxicity Data") rather than requiring the Agent to guess table names.
2.  **Hybrid Search (Relevance + Constraints):** Vector search alone is insufficient for GxP. We use **Hybrid Search**: Dense Retrieval (Vector) to find relevant data, combined with Symbolic Filtering (Metadata) to enforce hard constraints (e.g., "Must be Phase 3").
3.  **Governance-as-Code (OPA):** We reject hardcoded permission logic. We use **Open Policy Agent (OPA)** rules (Rego) attached to the data source. The Catalog evaluates these rules dynamically against the user's coreason-identity token at query time.
4.  **Cryptographic Provenance:** Every returned data packet is wrapped in a **W3C PROV** compliant envelope, stamping exactly *which* source provided the data and *when*.

## 3. Core Functional Requirements (Component Level)

### 3.1 The Hybrid Registry (The Map)

**Concept:** A Vector-Native Data Catalog.

*   **Storage Engine:** Uses **LanceDB** (Embedded).
    *   *Why:* LanceDB supports native **Hybrid Search** (Vectors + SQL Filtering) and stores data in Apache Arrow format, ensuring zero-copy compatibility with coreason-refinery.
*   **Mechanism:**
    *   Stores a SourceManifest for every registered MCP Server.
    *   Indexes the natural language descriptions and schema fields as embeddings.
*   **Query Logic:**
    *   *Agent Intent:* "I need PK/PD data for Monoclonal Antibodies."
    *   *Vector Search:* Matches Source A and Source B.
    *   *Output:* A list of candidate Source URNs sorted by semantic distance.

### 3.2 The Sovereignty Guard (The Firewall)

**Concept:** Attribute-Based Access Control (ABAC).

*   **Technology:** Embeds the **Open Policy Agent (OPA)** engine.
*   **Input Context:**
    *   **Subject:** User(location="US", role="Scientist_L2", project="Oncology") (from coreason-identity).
    *   **Object:** Source(geo="EU", license="GDPR_RESTRICTED", sensitivity="PII").
    *   **Action:** Query.
*   **Policy Logic:** Executes Rego: `allow { input.subject.location == input.object.geo }`.
*   **Action:** Silently filters out non-compliant sources from the routing list. The Agent is never told these sources exist (Security by Obscurity).

### 3.3 The Federation Broker (The Router)

**Concept:** The query dispatcher.

*   **Mechanism:**
    *   Takes the list of *Found* (Semantic) and *Allowed* (Policy) sources.
    *   **Protocol Translation:** Translates the Agent's high-level intent into specific MCP tool calls for each target.
    *   **Async Parallelism:** Queries all targets simultaneously via SSE (Server-Sent Events).
    *   **Aggregation:** Merges the results into a unified JSON response, de-duping where possible.

### 3.4 The Lineage Stamper (The Auditor)

**Concept:** Preserves the Chain of Custody.

*   **Standard:** Implements **W3C PROV-O** JSON-LD format.
*   **Action:** Appends a metadata footer to every response.
    ```json
    "_provenance": {
       "source_urn": "urn:coreason:mcp:hospital_mayo",
       "query_hash": "sha256:a1b2...",
       "policy_version": "v1.2",
       "retrieval_timestamp": "2026-01-11T12:00:00Z"
    }
    ```
*   **Value:** Essential for coreason-auditor to generate the Traceability Matrix.

## 4. Integration Requirements

*   **coreason-mcp (The Targets):**
    *   Each MCP server must implement a `get_manifest()` endpoint. coreason-catalog calls this during the registration phase to fetch the metadata for vectorization.
*   **coreason-cortex (The Consumer):**
    *   Cortex does not manage connections. It calls `catalog.find_and_query(intent="...")`.
    *   This decouples the reasoning logic from the physical network topology.
*   **coreason-veritas (The Log):**
    *   Catalog logs "Blocked Access Attempts."
    *   *Log Entry:* "User US_01 attempted query matching EU_Source. Action: BLOCKED by Policy GDPR_01."

## 5. User Stories

### Story A: The "Semantic Routing" (Discovery)

**Context:** Agent needs "Adverse Event logs for Aspirin."
**Problem:** The Agent doesn't know the table names or which database holds safety data.
**Catalog Action:**

1.  Embeds "Adverse Event logs...".
2.  **Hybrid Search:**
    *   *Filter:* `sensitivity != 'GxP_LOCKED'`
    *   *Vector:* Nearest Neighbor to "Adverse Events".
3.  Matches Source: FDA_FAERS and Source: Internal_Safety.
    *Result:* Routes query to both. Aggregates results.

### Story B: The "GDPR Firewall" (Sovereignty)

**Context:** US-based Agent queries "All Patient Vitals."
**Catalog Policy Engine:**

*   Source_Berlin_Hospital: Tagged `geo:EU`. Policy `Must be in EU`. -> **DROP**.
*   Source_Boston_Hospital: Tagged `geo:US`. Policy `None`. -> **PASS**.
    *Result:* The Agent receives data only from Boston. It is unaware the Berlin data even exists.

### Story C: The "Audit Trail" (Provenance)

**Context:** An FDA Auditor asks: "This generated report mentions a safety signal. Which specific database did that come from?"
**Action:** Inspects the JSON output stored in coreason-archive.
**Result:** Finds the `_provenance` tag: source: `urn:coreason:mcp:safety_db_v2`.
**Verification:** Cross-references the URN in the Catalog to prove it was a validated GxP source.

## 6. Data Schema

### SourceManifest

```python
class DataSensitivity(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    PII = "PII"           # Personally Identifiable Information
    GxP_LOCKED = "GxP_LOCKED"

class SourceManifest(BaseModel):
    urn: str                    # "urn:coreason:mcp:clin_data_01"
    name: str                   # "Phase 3 Clinical Data"
    description: str            # "Patient vitals and AE logs..." (Embedded for Search)
    endpoint_url: str           # "sse://10.0.0.5:8080"

    # Governance Metadata
    geo_location: str           # "EU"
    sensitivity: DataSensitivity
    owner_group: str            # "Safety_Team"

    # OPA Policy (Rego)
    access_policy: str          # "allow { input.user.geo == input.object.geo }"
```

### CatalogResponse

```python
class SourceResult(BaseModel):
    source_urn: str
    status: Literal["SUCCESS", "ERROR", "BLOCKED_BY_POLICY"]
    data: Any
    latency_ms: float

class CatalogResponse(BaseModel):
    query_id: UUID
    aggregated_results: List[SourceResult]
    provenance_signature: str   # W3C PROV signature
```

## 7. Implementation Directives for the Coding Agent

1.  **Vector Database:** Use **LanceDB** (embedded mode). It provides the SOTA performance required for Hybrid Search and integrates natively with Arrow tables, which fits the coreason-refinery ecosystem better than other options.
2.  **Policy Engine:** Use a Python wrapper for **OPA (Open Policy Agent)**. Policies must be stored as .rego files to allow security auditors to verify rules without reading Python code.
3.  **Connection Pooling:** The Catalog must maintain persistent SSE (Server-Sent Events) connections to the registered MCP servers to minimize latency during "Fan-Out" operations.
4.  **Fail-Safe Aggregation:** If a high-priority source is down (500 Error), the Catalog should return partial results with a `partial_content` warning flag, rather than failing the entire query.

`-> [Source A (US)] + [Source B (EU) - BLOCKED] -> Aggregator -> Provenance Stamped Output]`
