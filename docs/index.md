# coreason-catalog

**Dynamic Registry and Routing Plane for the CoReason Ecosystem**

`coreason-catalog` acts as the **Smart Proxy** and **Cartographer** for the CoReason data mesh. It provides a single "Virtual Database" interface to agents, performing **Semantic Discovery** and **Sovereignty Enforcement** transparently.

## Core Philosophy

"The Map controls the Territory. Route by Meaning, Filter by Policy."

*   **Register:** Sources register embeddings of their schema, not just names.
*   **Discover:** Agents find data via Semantic Search (meaning), not just keywords.
*   **Govern:** Policies (OPA) are evaluated at query time to ensure sovereignty.
*   **Stamp:** Every response is cryptographically stamped with W3C PROV lineage.

## Documentation

*   [Product Requirements (PRD)](prd.md): The detailed requirements and functional philosophy.
*   [Architecture](architecture.md): Deep dive into the Hybrid Registry, Sovereignty Guard, Federation Broker, and Lineage Stamper.
*   [Usage Guide](usage.md): Installation, client examples, and user stories.
