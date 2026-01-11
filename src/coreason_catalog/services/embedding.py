from typing import List

from fastembed import TextEmbedding


class EmbeddingService:
    """
    Service for generating vector embeddings from text using FastEmbed.
    Default model: 'BAAI/bge-small-en-v1.5' (Dimension: 384)
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        """
        Initialize the embedding model.

        Args:
            model_name: The name of the FastEmbed model to use.
        """
        self.model = TextEmbedding(model_name=model_name)
        self._embedding_dim = 384  # Default for bge-small-en-v1.5

    def embed_text(self, text: str) -> List[float]:
        """
        Embed a single text string.

        Args:
            text: The input text.

        Returns:
            A list of floats representing the embedding vector.
        """
        # embed returns a generator of numpy arrays, we take the first one and convert to list
        embeddings = list(self.model.embed([text]))
        return embeddings[0].tolist()  # type: ignore[no-any-return]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a batch of text strings.

        Args:
            texts: A list of input texts.

        Returns:
            A list of embedding vectors (lists of floats).
        """
        embeddings = list(self.model.embed(texts))
        return [e.tolist() for e in embeddings]

    @property
    def embedding_dim(self) -> int:
        """Return the dimension of the embeddings."""
        return self._embedding_dim
