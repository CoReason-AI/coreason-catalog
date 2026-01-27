# Architecture: The Cartographer

`coreason-catalog` serves as the **Dynamic Registry and Routing Plane** (The "Cartographer") for the CoReason ecosystem. It acts as an active gateway that mediates access to decentralized data sources based on semantic meaning and governance policies.

## Architectural Overview

The architecture follows a **Register-Discover-Govern-Stamp** loop, ensuring that every data access is semantically relevant, policy-compliant, and auditable.

The system is composed of four main components:

1.  **The Hybrid Registry** (The Map)
2.  **The Sovereignty Guard** (The Firewall)
3.  **The Federation Broker** (The Router)
4.  **The Lineage Stamper** (The Auditor)

![Architecture Diagram](https://placehold.co/600x400?text=Architecture+Diagram+Placeholder)

## 1. The Hybrid Registry (The Map)

This component is responsible for knowing *what* data exists across the mesh and *where* it is located.

*   **Role:** Vector-Native Data Catalog.
*   **Storage Engine:** **LanceDB** (Embedded).
    *   LanceDB is chosen for its native support of **Hybrid Search** (Vector similarity + SQL-like filtering) and zero-copy compatibility with Apache Arrow.
*   **Functionality:**
    *   **Registration:** Stores a `SourceManifest` for each MCP Server.
    *   **Indexing:** Embeds natural language descriptions and schema fields for semantic retrieval.
    *   **Search:** Performs vector search to find sources matching an agent's intent (e.g., "Find Toxicity Data").
    *   **Zero-Copy:** Stores `source_pointer` to external data (e.g. drive ID, item ID) instead of raw content.

## 2. The Sovereignty Guard (The Firewall)

This component enforces data sovereignty and access control *before* any data is retrieved.

*   **Role:** Attribute-Based Access Control (ABAC) engine.
*   **Technology:** **Open Policy Agent (OPA)**.
*   **Functionality:**
    *   **Delegated Identity:** Enforces strict `UserContext` propagation and validation.
    *   **Context Evaluation:** Takes the User Context (Subject), Source Metadata (Object), and Query (Action).
    *   **Policy Execution:** Runs Rego policies (e.g., `allow { input.subject.location == input.object.geo }`).
    *   **Filtering:** Silently filters out sources that the user is not authorized to access. This ensures "Security by Obscurity"—agents are not even aware of restricted sources.

## 3. The Federation Broker (The Router)

This component manages the physical connections and query dispatch to the distributed data sources.

*   **Role:** Query Dispatcher and Aggregator.
*   **Functionality:**
    *   **Dispatch:** Takes the list of semantically relevant and policy-allowed sources.
    *   **Protocol Translation:** Converts high-level intents into specific MCP tool calls.
    *   **Parallel Execution:** Queries multiple targets concurrently using **SSE (Server-Sent Events)** for efficiency.
    *   **Aggregation:** Merges results from multiple sources into a unified response. It handles partial failures gracefully (returning partial content if some sources are down).

## 4. The Lineage Stamper (The Auditor)

This component ensures every piece of data can be traced back to its origin.

*   **Role:** Chain of Custody preserver.
*   **Standard:** **W3C PROV-O** (JSON-LD).
*   **Functionality:**
    *   **Stamping:** Appends a `_provenance` metadata footer to every response.
    *   **Details:** Includes `source_urn`, `query_hash`, `policy_version`, and `retrieval_timestamp`.
    *   **Audit:** Enables `coreason-auditor` to generate Traceability Matrices for GxP compliance.

## Data Flow

1.  **Registration:** MCP Servers register their `SourceManifest` (including embeddings and policies) with the Catalog.
2.  **Intent:** An Agent (via `coreason-cortex`) submits a query with a natural language intent (e.g., "I need PK/PD data").
3.  **Discovery:** The **Hybrid Registry** finds relevant sources using vector search.
4.  **Governance:** The **Sovereignty Guard** filters these sources based on the user's identity and the source's OPA policies.
5.  **Routing:** The **Federation Broker** dispatches the query to the remaining allowed sources in parallel.
6.  **Response:** The Broker aggregates the results.
7.  **Stamping:** The **Lineage Stamper** adds provenance metadata.
8.  **Output:** The final JSON response is returned to the Agent.
