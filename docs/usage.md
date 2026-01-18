# Usage Guide

This guide covers how to install, configure, and use `coreason-catalog`.

## Installation

`coreason-catalog` is managed with Poetry.

```bash
git clone https://github.com/CoReason-AI/coreason_catalog.git
cd coreason_catalog
poetry install
```

To run the server locally:

```bash
poetry run uvicorn coreason_catalog.main:app --reload
```

## Client Usage

The catalog exposes a REST API for registering sources and querying data. Below are Python examples using `httpx`.

### 1. Registering a Data Source

MCP Servers must register themselves with the Catalog to be discoverable.

```python
import httpx

# The manifest defines the source's metadata, embeddings (implied in description), and policy.
manifest = {
    "urn": "urn:coreason:mcp:clin_data_01",
    "name": "Phase 3 Clinical Data",
    "description": "Patient vitals, adverse event logs, and PK/PD data for Monoclonal Antibodies.",
    "endpoint_url": "sse://10.0.0.5:8080",
    "geo_location": "EU",
    "sensitivity": "PII",
    "owner_group": "Safety_Team",
    # OPA Rego Policy: Allow access only if the user is in the same location as the data.
    "access_policy": "allow { input.user.location == input.object.geo_location }"
}

response = httpx.post("http://localhost:8000/v1/sources", json=manifest)
print(response.json())
# Output: {'status': 'registered', 'urn': 'urn:coreason:mcp:clin_data_01'}
```

### 2. Querying the Catalog

Agents (like `coreason-cortex`) query the catalog with a high-level intent. The catalog handles discovery, governance, and routing.

```python
import httpx

query_request = {
    "intent": "I need PK/PD data for Monoclonal Antibodies.",
    "user_context": {
        "user": {
            "id": "user_123",
            "location": "EU",
            "role": "Scientist_L2"
        }
    },
    "limit": 5
}

response = httpx.post("http://localhost:8000/v1/query", json=query_request)
result = response.json()

print(f"Query ID: {result['query_id']}")
for source_result in result['aggregated_results']:
    print(f"Source: {source_result['source_urn']} - Status: {source_result['status']}")
    # print(source_result['data'])

print(f"Provenance: {result['provenance_signature']}")
```

## Vignettes (User Stories)

These scenarios illustrate how `coreason-catalog` behaves in real-world situations.

### Story A: Semantic Routing (Discovery)

**Context:** An Agent needs "Adverse Event logs for Aspirin."
**Problem:** The Agent doesn't know the table names or which database holds safety data.

**Process:**
1.  **Intent:** The Agent sends the intent "Adverse Event logs for Aspirin".
2.  **Hybrid Search:** The Catalog embeds this intent and searches its Vector Database (LanceDB).
    *   It filters out sources with `sensitivity == 'GxP_LOCKED'`.
    *   It finds sources semantically close to "Adverse Events".
3.  **Routing:** It identifies `urn:coreason:mcp:fda_faers` and `urn:coreason:mcp:internal_safety`.
4.  **Result:** The Catalog queries both sources and aggregates the results.

### Story B: The GDPR Firewall (Sovereignty)

**Context:** A US-based Agent queries "All Patient Vitals."

**User Context:** `{"location": "US"}`

**Sources:**
*   **Source Berlin:** `urn:coreason:mcp:berlin_hospital`
    *   **Tag:** `geo:EU`
    *   **Policy:** `allow { input.user.location == "EU" }`
*   **Source Boston:** `urn:coreason:mcp:boston_hospital`
    *   **Tag:** `geo:US`
    *   **Policy:** `allow { input.user.location == "US" }` (or no restriction)

**Process:**
1.  The Catalog evaluates OPA policies for both potential matches.
2.  **Berlin:** `input.user.location` ("US") != "EU". **DENY**.
3.  **Boston:** `input.user.location` ("US") == "US". **ALLOW**.

**Result:** The Agent receives data *only* from Boston. The existence of the Berlin source is hidden from the response to prevent data leakage.

### Story C: The Audit Trail (Provenance)

**Context:** An FDA Auditor asks: "This generated report mentions a safety signal. Which specific database did that come from?"

**Process:**
1.  The Auditor inspects the JSON output stored in `coreason-archive`.
2.  They look for the `_provenance` footer in the response.

```json
"_provenance": {
   "source_urn": "urn:coreason:mcp:safety_db_v2",
   "query_hash": "sha256:a1b2c3d4...",
   "policy_version": "v1.2",
   "retrieval_timestamp": "2026-01-11T12:00:00Z"
}
```

**Result:** The URN `urn:coreason:mcp:safety_db_v2` uniquely identifies the source. The timestamp and hash provide cryptographic proof of the data's origin and state at that time.
