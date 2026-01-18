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
[![CI/CD](https://github.com/CoReason-AI/coreason-catalog/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/CoReason-AI/coreason-catalog/actions/workflows/ci-cd.yml)
[![Docker](https://github.com/CoReason-AI/coreason-catalog/actions/workflows/docker.yml/badge.svg)](https://github.com/CoReason-AI/coreason-catalog/actions/workflows/docker.yml)
[![Publish](https://github.com/CoReason-AI/coreason-catalog/actions/workflows/publish.yml/badge.svg)](https://github.com/CoReason-AI/coreason-catalog/actions/workflows/publish.yml)
[![PyPI version](https://img.shields.io/pypi/v/coreason-catalog.svg)](https://pypi.org/project/coreason-catalog/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/coreason-catalog.svg)](https://pypi.org/project/coreason-catalog/)
[![codecov](https://codecov.io/gh/CoReason-AI/coreason-catalog/branch/main/graph/badge.svg)](https://codecov.io/gh/CoReason-AI/coreason-catalog)
[![License](https://img.shields.io/badge/license-Prosperity_3.0-blue)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)

## Getting Started

### Prerequisites

-   Python 3.12+
-   Poetry

### Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/CoReason-AI/coreason-catalog.git
    cd coreason-catalog
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
