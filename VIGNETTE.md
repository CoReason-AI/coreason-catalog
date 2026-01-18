# The Architecture and Utility of coreason-catalog

### 1. The Philosophy (The Why)

In the decentralized landscape of a modern Bio-Pharma Data Mesh, data sovereignty and discovery are persistent bottlenecks. Clinical data resides in siloed hospital networks, research findings in proprietary lab servers, and toxicity logs in third-party vendor databases. Expecting a Reasoning Engine (like `coreason-cortex`) to navigate this physical topology—managing IP addresses, schema variations, and complex GDPR/GxP compliance rules—is an architectural anti-pattern.

`coreason-catalog` was built to solve this by acting as the **"Cartographer"** and **"Smart Proxy"** for the ecosystem. Its core philosophy is that **"The Map controls the Territory."** Instead of the agent guessing where data lives, it expresses an *intent*, and the Catalog routes that intent to the correct sources based on *meaning* rather than location.

Critically, this package enforces **Sovereignty-as-Code**. By embedding the governance layer directly into the routing plane, `coreason-catalog` ensures that a US-based agent never accidentally queries a GDPR-restricted European server. The agent simply asks, and the Catalog silently filters out the "unreachable" parts of the world, providing a clean, compliant virtual database interface.

### 2. Under the Hood (The Dependencies & logic)

The `coreason-catalog` stack is chosen to balance high-performance search with strict governance verification:

*   **`lancedb`**: This embedded vector database is the engine behind the "Hybrid Search" capability. It allows the catalog to store embeddings of source descriptions and schemas, enabling semantic retrieval (finding sources by meaning) while supporting SQL filtering for metadata constraints. Its use of Apache Arrow ensures zero-copy data handling.
*   **`fastembed`**: Used to generate lightweight, high-quality vector embeddings for both source manifests and incoming user queries, facilitating the semantic matching process.
*   **`open-policy-agent` (OPA)**: The package integrates a wrapper around the OPA engine to execute Rego policies. This moves permission logic out of Python `if` statements and into declarative policy files, allowing for auditable, attribute-based access control (ABAC).
*   **`asyncio` & `httpx`**: To handle the "fan-out" nature of federated queries, the architecture relies on asynchronous IO to dispatch requests to multiple MCP servers in parallel, minimizing latency.
*   **`pydantic`**: Ensures rigorous data validation for the Source Manifests and the internal messaging protocols.

**The Logic Flow:**
When a query arrives, the `FederationBroker` orchestrates a four-step loop:
1.  **Embed & Search:** The user's intent is vectorized and matched against the `lancedb` registry to find semantically relevant sources.
2.  **Govern:** Before any connection is made, the OPA engine evaluates the `access_policy` of each candidate source against the user's identity context. Sources that return `false` are silently dropped.
3.  **Dispatch:** Validated intents are translated into specific MCP tool calls and dispatched asynchronously to all "Found" and "Allowed" sources.
4.  **Stamp:** Aggregated results are wrapped in a W3C PROV-compliant envelope, ensuring every data point has a cryptographic chain of custody.

### 3. In Practice (The How)

Using `coreason-catalog` involves two primary activities: registering data sources with their governance rules and dispatching intent-based queries.

**Defining a Sovereign Source**
A `SourceManifest` does not just describe *where* data is, but *what* it is and *who* can access it. Notice the embedded Rego policy that restricts access based on geolocation.

```python
from coreason_catalog.models import SourceManifest, DataSensitivity

# A Clinical Data Source located in the EU with GDPR restrictions
eu_clinical_source = SourceManifest(
    urn="urn:coreason:mcp:berlin_clinic_01",
    name="Berlin Phase 3 Trials",
    description="Patient vitals, demographics, and adverse event logs for Phase 3 oncology trials.",
    endpoint_url="sse://10.20.0.5:8080",
    geo_location="EU",
    sensitivity=DataSensitivity.PII,
    owner_group="Clinical_Ops_EU",
    # OPA Rego Policy: Allow only if the requester is also in the EU
    access_policy="""
    package match
    default allow = false
    allow {
        input.subject.location == input.object.geo
    }
    """
)
```

**The Federation Loop**
The `FederationBroker` abstracts the complexity of the network. The consumer provides a high-level intent and their context; the Broker handles the rest.

```python
import asyncio
from coreason_catalog.services.broker import FederationBroker

# Assume services (vector_store, policy_engine, etc.) are initialized
broker = FederationBroker(
    vector_store=vector_store,
    policy_engine=policy_engine,
    embedding_service=embedding_service,
    dispatcher=dispatcher,
    provenance_service=provenance_service
)

# User Context: A US-based Scientist
user_context = {
    "user_id": "dr_smith",
    "role": "Scientist_L2",
    "location": "US",  # Note: This will cause the EU source above to be filtered out
    "project": "Oncology"
}

# The Broker executes the Discovery -> Governance -> Dispatch -> Aggregation loop
response = await broker.dispatch_query(
    intent="Find all adverse events related to monoclonal antibodies.",
    user_context=user_context
)

# The response contains data only from allowed sources (e.g., US labs),
# automatically aggregated and stamped with provenance.
print(f"Query ID: {response.query_id}")
for result in response.aggregated_results:
    print(f"Source: {result.source_urn} | Status: {result.status}")
```
