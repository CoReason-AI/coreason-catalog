# coreason-catalog

**Dynamic Registry and Routing Plane for the CoReason Ecosystem**

`coreason-catalog` serves as the "Cartographer" and active gateway for the CoReason data mesh. It enables agents to discover data sources based on semantic meaning and enforces data sovereignty policies at query time.

**Core Philosophy:** "The Map controls the Territory. Route by Meaning, Filter by Policy."

## Documentation

Full documentation is available in the `docs/` folder:

-   **[Home](docs/index.md)**
-   **[Product Requirements (PRD)](docs/prd.md)**
-   **[Architecture](docs/architecture.md)**
-   **[Usage Guide](docs/usage.md)**

## Getting Started

### Prerequisites

-   Python 3.12+
-   Poetry

### Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/CoReason-AI/coreason_catalog.git
    cd coreason_catalog
    ```
2.  Install dependencies:
    ```bash
    poetry install
    ```

### Running the Server

To start the catalog server locally:

```bash
poetry run uvicorn coreason_catalog.main:app --reload
```

### Development

-   Run the linter:
    ```bash
    poetry run pre-commit run --all-files
    ```
-   Run the tests:
    ```bash
    poetry run pytest
    ```
