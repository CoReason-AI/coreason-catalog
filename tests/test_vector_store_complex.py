import concurrent.futures
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from coreason_catalog.models import DataSensitivity, SourceManifest
from coreason_catalog.services.vector_store import VectorStore


@pytest.fixture
def test_db_path_complex(tmp_path: Path) -> Generator[str, None, None]:
    """Fixture to provide a temporary path for the database."""
    path = tmp_path / "test_lancedb_complex"
    yield str(path)


@pytest.fixture
def vector_store_complex(test_db_path_complex: str) -> VectorStore:
    return VectorStore(uri=test_db_path_complex)


@pytest.fixture
def sample_manifest() -> SourceManifest:
    return SourceManifest(
        urn="urn:coreason:mcp:test_complex",
        name="Complex Test DB",
        description="Data for complex testing",
        endpoint_url="sse://localhost:8081",
        geo_location="US",
        sensitivity=DataSensitivity.INTERNAL,
        owner_group="DevOps",
        access_policy="allow { true }",
    )


def test_search_no_results(vector_store_complex: VectorStore) -> None:
    """Test searching when no data exists or no matches found."""
    # Empty DB search
    embedding = [0.1] * 384
    results = vector_store_complex.search(embedding)
    assert len(results) == 0
    assert isinstance(results, list)


def test_invalid_vector_dimension(vector_store_complex: VectorStore, sample_manifest: SourceManifest) -> None:
    """Test that invalid vector dimensions raise ValueError."""
    # Wrong dimension for add
    bad_embedding = [0.1] * 10
    with pytest.raises(ValueError, match="dimension mismatch"):
        vector_store_complex.add_source(sample_manifest, bad_embedding)

    # Wrong dimension for search
    with pytest.raises(ValueError, match="dimension mismatch"):
        vector_store_complex.search(bad_embedding)


def test_invalid_filter_sql(vector_store_complex: VectorStore, sample_manifest: SourceManifest) -> None:
    """Test that invalid SQL in filter raises ValueError."""
    embedding = [0.1] * 384
    vector_store_complex.add_source(sample_manifest, embedding)

    with pytest.raises((ValueError, RuntimeError), match="Search failed"):
        # Note: LanceDB might raise a generic Arrow/Dataset error for invalid SQL syntax
        # We catch RuntimeError in our wrapper if it's not strictly caught as ValueError
        vector_store_complex.search(embedding, filter_sql="INVALID SQL SYNTAX")


def test_duplicate_urn_handling(vector_store_complex: VectorStore, sample_manifest: SourceManifest) -> None:
    """Test that adding the same URN updates it rather than duplicating."""
    embedding = [0.1] * 384

    # First add
    vector_store_complex.add_source(sample_manifest, embedding)

    # Second add (update description)
    updated = sample_manifest.model_copy(update={"description": "Updated Desc"})
    vector_store_complex.add_source(updated, embedding)

    # Verify count is 1 and data is updated
    results = vector_store_complex.search(embedding)
    assert len(results) == 1
    assert results[0].description == "Updated Desc"


def test_concurrent_writes(vector_store_complex: VectorStore) -> None:
    """Test concurrent writes to ensure no crashes (though LWW or race conditions might occur on data)."""

    def write_op(i: int) -> str:
        manifest = SourceManifest(
            urn=f"urn:concurrent:{i}",
            name=f"Source {i}",
            description=f"Desc {i}",
            endpoint_url="sse://locahost",
            geo_location="US",
            sensitivity=DataSensitivity.PUBLIC,
            owner_group="Group",
            access_policy="",
        )
        embedding = [0.1] * 384
        try:
            vector_store_complex.add_source(manifest, embedding)
            return "OK"
        except Exception as e:
            return str(e)

    # Launch 10 threads writing simultaneously
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(write_op, i) for i in range(10)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    # Ensure all writes succeeded (no critical DB lock errors)
    # LanceDB handles concurrency reasonably well for appends, but our delete-insert might race.
    # We just want to ensure it doesn't crash the process.
    assert all(r == "OK" for r in results)

    # Check count
    # Since we use unique URNs, we should have 10 items
    search_res = vector_store_complex.search([0.1] * 384, limit=20)
    assert len(search_res) == 10


def test_add_source_runtime_error(vector_store_complex: VectorStore, sample_manifest: SourceManifest) -> None:
    """Test that generic exceptions during add_source are caught and re-raised as RuntimeError."""
    embedding = [0.1] * 384

    # Mock open_table to raise an exception
    with patch.object(vector_store_complex.db, "open_table", side_effect=Exception("DB connection lost")):
        with pytest.raises(RuntimeError, match="Failed to add source: DB connection lost"):
            vector_store_complex.add_source(sample_manifest, embedding)


def test_search_runtime_error(vector_store_complex: VectorStore) -> None:
    """Test that generic exceptions during search are caught and re-raised as RuntimeError."""
    embedding = [0.1] * 384

    # Mock open_table to raise an exception
    with patch.object(vector_store_complex.db, "open_table", side_effect=Exception("Search Error")):
        with pytest.raises(RuntimeError, match="Search failed: Search Error"):
            vector_store_complex.search(embedding)


def test_search_sql_syntax_error(vector_store_complex: VectorStore, sample_manifest: SourceManifest) -> None:
    """Test that SQL syntax errors are specifically identified if possible, otherwise generic runtime."""
    embedding = [0.1] * 384
    vector_store_complex.add_source(sample_manifest, embedding)

    # We deliberately inject an error that to_pandas might raise if the query plan is invalid
    # Mocking query.to_pandas to raise a specific Syntax Error message

    # Create a mock query object
    mock_query = MagicMock()
    mock_query.limit.return_value = mock_query
    mock_query.where.return_value = mock_query
    mock_query.to_pandas.side_effect = Exception("syntax error at or near")

    mock_table = MagicMock()
    mock_table.search.return_value = mock_query

    with patch.object(vector_store_complex.db, "open_table", return_value=mock_table):
        with pytest.raises(ValueError, match="Invalid SQL filter"):
            vector_store_complex.search(embedding, filter_sql="BAD SQL")
