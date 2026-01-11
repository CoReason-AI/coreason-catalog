import numpy as np
import pytest
from pytest_mock import MockerFixture

from coreason_catalog.services.embedding import EmbeddingService

# We mock TextEmbedding to avoid downloading models during tests
# unless we explicitly want integration tests.
# For unit tests, we should mock.


@pytest.fixture  # type: ignore[misc]
def mock_embedding_model(mocker: MockerFixture) -> object:
    mock_model = mocker.Mock()

    # Mock return value of embed: a generator yielding numpy arrays
    def mock_embed(texts: list[str]) -> object:
        for _ in texts:
            yield np.array([0.1, 0.2, 0.3])

    mock_model.embed.side_effect = mock_embed

    # Patch the TextEmbedding class
    mocker.patch("coreason_catalog.services.embedding.TextEmbedding", return_value=mock_model)
    return mock_model


def test_embedding_service_initialization(mock_embedding_model: MockerFixture) -> None:
    service = EmbeddingService()
    assert service.embedding_dim == 384
    # Check that TextEmbedding was instantiated
    # import coreason_catalog.services.embedding
    # coreason_catalog.services.embedding.TextEmbedding.assert_called_once() # This is tricky because of import

    # We can check via the mock_embedding_model if we had access to the class constructor mock
    # But here we just verify the service was created


def test_embed_text(mock_embedding_model: MockerFixture) -> None:
    service = EmbeddingService()
    vector = service.embed_text("Hello world")

    assert isinstance(vector, list)
    assert len(vector) == 3  # Based on our mock
    assert vector == [0.1, 0.2, 0.3]

    # Verify mock call
    service.model.embed.assert_called_with(["Hello world"])


def test_embed_batch(mock_embedding_model: MockerFixture) -> None:
    service = EmbeddingService()
    texts = ["Hello", "World"]
    vectors = service.embed_batch(texts)

    assert isinstance(vectors, list)
    assert len(vectors) == 2
    assert vectors[0] == [0.1, 0.2, 0.3]
    assert vectors[1] == [0.1, 0.2, 0.3]

    service.model.embed.assert_called_with(texts)
