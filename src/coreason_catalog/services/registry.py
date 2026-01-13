from typing import List

from coreason_catalog.models import SourceManifest
from coreason_catalog.services.embedding import EmbeddingService
from coreason_catalog.services.vector_store import VectorStore
from coreason_catalog.utils.logger import logger


class RegistryService:
    """
    Service for managing the lifecycle of Source Manifests in the Hybrid Registry.
    Handles semantic registration (embedding generation) and persistence.
    """

    def __init__(self, vector_store: VectorStore, embedding_service: EmbeddingService):
        """
        Initialize the Registry Service.

        Args:
            vector_store: The storage engine (LanceDB wrapper).
            embedding_service: The service for generating embeddings.
        """
        self.vector_store = vector_store
        self.embedding_service = embedding_service

    def register_source(self, manifest: SourceManifest) -> None:
        """
        Register a new source or update an existing one.
        Generates an embedding for the source description and stores it.

        Args:
            manifest: The source manifest to register.

        Raises:
            ValueError: If embedding generation fails or returns invalid dimension.
            RuntimeError: If storage fails.
        """
        logger.info(f"Registering source: {manifest.name} ({manifest.urn})")

        # 1. Generate Embedding
        # We embed the description. In the future, we might concatenate other fields
        # or use a more complex representation as per PRD "Indexes... schema fields".
        # For now, description is the primary semantic field.
        try:
            embedding: List[float] = self.embedding_service.embed_text(manifest.description)
        except Exception as e:
            logger.error(f"Failed to generate embedding for source {manifest.urn}: {e}")
            raise ValueError(f"Failed to generate embedding: {e}") from e

        # Validate embedding dimension (fail-fast)
        if len(embedding) != self.embedding_service.embedding_dim:
            msg = (
                f"Generated embedding dimension {len(embedding)} "
                f"does not match expected {self.embedding_service.embedding_dim}"
            )
            logger.error(msg)
            raise ValueError(msg)

        # 2. Store in Vector Database
        try:
            self.vector_store.add_source(manifest, embedding)
            logger.info(f"Successfully registered source {manifest.urn}")
        except Exception as e:
            logger.error(f"Failed to store source {manifest.urn} in vector store: {e}")
            raise RuntimeError(f"Failed to store source: {e}") from e
