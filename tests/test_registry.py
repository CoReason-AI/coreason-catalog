from unittest.mock import MagicMock

import pytest
from coreason_catalog.models import DataSensitivity, SourceManifest
from coreason_catalog.services.embedding import EmbeddingService
from coreason_catalog.services.registry import RegistryService
from coreason_catalog.services.vector_store import VectorStore


@pytest.fixture  # type: ignore[misc]
def mock_vector_store() -> MagicMock:
    return MagicMock(spec=VectorStore)


@pytest.fixture  # type: ignore[misc]
def mock_embedding_service() -> MagicMock:
    service = MagicMock(spec=EmbeddingService)
    # Default behavior: return a dummy embedding of correct size (384)
    service.embed_text.return_value = [0.1] * 384
    service.embedding_dim = 384
    return service


@pytest.fixture  # type: ignore[misc]
def registry_service(mock_vector_store: MagicMock, mock_embedding_service: MagicMock) -> RegistryService:
    return RegistryService(vector_store=mock_vector_store, embedding_service=mock_embedding_service)


@pytest.fixture  # type: ignore[misc]
def sample_manifest() -> SourceManifest:
    return SourceManifest(
        urn="urn:coreason:mcp:test_source",
        name="Test Source",
        description="A test source description.",
        endpoint_url="sse://localhost:8000",
        geo_location="US",
        sensitivity=DataSensitivity.PUBLIC,
        owner_group="TestGroup",
        access_policy="allow { true }",
    )


def test_register_source_success(
    registry_service: RegistryService,
    mock_vector_store: MagicMock,
    mock_embedding_service: MagicMock,
    sample_manifest: SourceManifest,
) -> None:
    """Test successful registration of a source."""
    registry_service.register_source(sample_manifest)

    # Verify embedding called with description
    mock_embedding_service.embed_text.assert_called_once_with(sample_manifest.description)

    # Verify vector store add called with manifest and embedding
    expected_embedding = [0.1] * 384
    mock_vector_store.add_source.assert_called_once_with(sample_manifest, expected_embedding)


def test_register_source_embedding_failure(
    registry_service: RegistryService,
    mock_embedding_service: MagicMock,
    sample_manifest: SourceManifest,
) -> None:
    """Test failure when embedding generation fails."""
    mock_embedding_service.embed_text.side_effect = Exception("Embedding model error")

    with pytest.raises(ValueError, match="Failed to generate embedding"):
        registry_service.register_source(sample_manifest)


def test_register_source_dimension_mismatch(
    registry_service: RegistryService,
    mock_embedding_service: MagicMock,
    sample_manifest: SourceManifest,
) -> None:
    """Test failure when embedding dimension is incorrect."""
    mock_embedding_service.embed_text.return_value = [0.1] * 10  # Wrong dimension
    mock_embedding_service.embedding_dim = 384

    with pytest.raises(ValueError, match="Generated embedding dimension"):
        registry_service.register_source(sample_manifest)


def test_register_source_storage_failure(
    registry_service: RegistryService,
    mock_vector_store: MagicMock,
    sample_manifest: SourceManifest,
) -> None:
    """Test failure when vector store storage fails."""
    mock_vector_store.add_source.side_effect = Exception("DB Error")

    with pytest.raises(RuntimeError, match="Failed to store source"):
        registry_service.register_source(sample_manifest)


def test_register_source_empty_description(
    registry_service: RegistryService,
    mock_vector_store: MagicMock,
    mock_embedding_service: MagicMock,
    sample_manifest: SourceManifest,
) -> None:
    """Test registration with an empty description."""
    sample_manifest.description = ""
    registry_service.register_source(sample_manifest)

    # Should still attempt to embed empty string
    mock_embedding_service.embed_text.assert_called_once_with("")
    mock_vector_store.add_source.assert_called_once()


def test_register_source_whitespace_description(
    registry_service: RegistryService,
    mock_vector_store: MagicMock,
    mock_embedding_service: MagicMock,
    sample_manifest: SourceManifest,
) -> None:
    """Test registration with a whitespace-only description."""
    sample_manifest.description = "   "
    registry_service.register_source(sample_manifest)

    # Should still attempt to embed whitespace string
    mock_embedding_service.embed_text.assert_called_once_with("   ")
    mock_vector_store.add_source.assert_called_once()


def test_register_source_update_scenario(
    registry_service: RegistryService,
    mock_vector_store: MagicMock,
    mock_embedding_service: MagicMock,
    sample_manifest: SourceManifest,
) -> None:
    """
    Test a scenario where a source is updated.
    1. Register with original description.
    2. Register with new description.
    Verify that embedding is regenerated and stored each time.
    """
    # 1. First Registration
    registry_service.register_source(sample_manifest)
    mock_embedding_service.embed_text.assert_called_with(sample_manifest.description)
    mock_vector_store.add_source.assert_called_with(sample_manifest, [0.1] * 384)

    # Reset mocks to track second call cleanly
    mock_embedding_service.embed_text.reset_mock()
    mock_vector_store.add_source.reset_mock()

    # 2. Update Description
    new_description = "Updated description for the same source."
    sample_manifest.description = new_description
    # Simulate a different embedding for the new text
    new_embedding = [0.2] * 384
    mock_embedding_service.embed_text.return_value = new_embedding

    registry_service.register_source(sample_manifest)

    # Verify new embedding was generated
    mock_embedding_service.embed_text.assert_called_once_with(new_description)
    # Verify new embedding was stored
    mock_vector_store.add_source.assert_called_once_with(sample_manifest, new_embedding)
