from pathlib import Path
from typing import Generator

import pytest

from coreason_catalog.models import DataSensitivity, SourceManifest
from coreason_catalog.services.vector_store import VectorStore


@pytest.fixture  # type: ignore[misc]
def test_db_path(tmp_path: Path) -> Generator[str, None, None]:
    """Fixture to provide a temporary path for the database."""
    path = tmp_path / "test_lancedb"
    yield str(path)
    # Cleanup is handled by tmp_path, but lancedb might leave locks?
    # Usually tmp_path is safe.


@pytest.fixture  # type: ignore[misc]
def vector_store(test_db_path: str) -> VectorStore:
    return VectorStore(uri=test_db_path)


@pytest.fixture  # type: ignore[misc]
def sample_manifest() -> SourceManifest:
    return SourceManifest(
        urn="urn:coreason:mcp:test_01",
        name="Test Database",
        description="Clinical trials data for oncology",
        endpoint_url="sse://localhost:8080",
        geo_location="US",
        sensitivity=DataSensitivity.PII,
        owner_group="Oncology_Dept",
        access_policy="allow { true }",
    )


def test_init_creates_table(vector_store: VectorStore) -> None:
    assert "sources" in vector_store.db.list_tables().tables


def test_add_and_search_source(vector_store: VectorStore, sample_manifest: SourceManifest) -> None:
    # Create a mock embedding (dimension 384)
    embedding = [0.1] * 384

    vector_store.add_source(sample_manifest, embedding)

    # Search with the same vector
    results = vector_store.search(embedding, limit=1)

    assert len(results) == 1
    assert results[0].urn == sample_manifest.urn
    assert results[0].name == sample_manifest.name
    assert results[0].sensitivity == DataSensitivity.PII


def test_search_filtering(vector_store: VectorStore) -> None:
    # Add two sources
    m1 = SourceManifest(
        urn="urn:1",
        name="S1",
        description="D1",
        endpoint_url="url",
        geo_location="US",
        sensitivity="PUBLIC",
        owner_group="G1",
        access_policy="",
    )
    m2 = SourceManifest(
        urn="urn:2",
        name="S2",
        description="D2",
        endpoint_url="url",
        geo_location="EU",
        sensitivity="PUBLIC",
        owner_group="G1",
        access_policy="",
    )

    embedding = [0.1] * 384
    vector_store.add_source(m1, embedding)
    vector_store.add_source(m2, embedding)

    # Filter for US
    results_us = vector_store.search(embedding, filter_sql="geo_location = 'US'")
    assert len(results_us) == 1
    assert results_us[0].urn == "urn:1"

    # Filter for EU
    results_eu = vector_store.search(embedding, filter_sql="geo_location = 'EU'")
    assert len(results_eu) == 1
    assert results_eu[0].urn == "urn:2"


def test_upsert_behavior(vector_store: VectorStore, sample_manifest: SourceManifest) -> None:
    embedding = [0.1] * 384
    vector_store.add_source(sample_manifest, embedding)

    # Update description
    updated_manifest = sample_manifest.model_copy(update={"description": "Updated Description"})
    vector_store.add_source(updated_manifest, embedding)

    results = vector_store.search(embedding)
    assert len(results) == 1
    assert results[0].description == "Updated Description"
