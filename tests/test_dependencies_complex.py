# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_catalog

import concurrent.futures
from unittest.mock import MagicMock, patch

import pytest
from coreason_catalog.dependencies import (
    get_embedding_service,
    get_federation_broker,
    get_registry_service,
    get_vector_store,
)
from coreason_catalog.services.broker import FederationBroker
from coreason_catalog.services.registry import RegistryService
from coreason_catalog.services.vector_store import VectorStore
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient


def test_singleton_concurrency() -> None:
    """
    Verify that get_vector_store returns the same instance even when called
    concurrently from multiple threads.
    """
    with patch("coreason_catalog.services.vector_store.lancedb.connect") as mock_connect:
        # Setup mock
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.list_tables.return_value.tables = []

        # Clear cache to ensure fresh start
        get_vector_store.cache_clear()  # type: ignore[attr-defined]

        def get_vs_instance() -> VectorStore:
            return get_vector_store()

        # Run 10 threads trying to get the instance
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(get_vs_instance) for _ in range(10)]
            results = [f.result() for f in futures]

        # Assert all results are the exact same object
        first_instance = results[0]
        for instance in results[1:]:
            assert instance is first_instance

        # Verify init was called only once
        mock_connect.assert_called_once()


def test_initialization_error_propagation() -> None:
    """
    Verify that if the underlying service raises an error during init,
    the dependency provider propagates it.
    """
    get_embedding_service.cache_clear()  # type: ignore[attr-defined]

    with patch("coreason_catalog.services.embedding.TextEmbedding") as mock_embed:
        mock_embed.side_effect = RuntimeError("Model download failed")

        try:
            get_embedding_service()
        except RuntimeError as e:
            assert str(e) == "Model download failed"
        else:
            pytest.fail("Should have raised RuntimeError")


def test_dependency_graph_resolution() -> None:
    """
    Verify the 'Diamond Dependency' scenario:
    RegistryService and FederationBroker both depend on VectorStore.
    In a FastAPI request, they should receive the EXACT SAME VectorStore instance.
    """
    # Clear caches
    get_vector_store.cache_clear()  # type: ignore[attr-defined]
    get_embedding_service.cache_clear()  # type: ignore[attr-defined]

    # Mock the heavyweight internals to avoid real IO
    with (
        patch("coreason_catalog.services.vector_store.lancedb.connect") as mock_connect,
        patch("coreason_catalog.services.embedding.TextEmbedding"),
    ):
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.list_tables.return_value.tables = []

        app = FastAPI()

        @app.get("/test-graph")  # type: ignore[misc]
        def check_dependencies(
            registry: RegistryService = Depends(get_registry_service),  # noqa: B008
            broker: FederationBroker = Depends(get_federation_broker),  # noqa: B008
            vector_store: VectorStore = Depends(get_vector_store),  # noqa: B008
        ) -> dict[str, bool]:
            # The core test: are the instances shared?

            # 1. Registry's VS should be the same as Broker's VS
            vs_shared_registry_broker = registry.vector_store is broker.vector_store

            # 2. Registry's VS should be the same as the VS injected directly
            vs_shared_registry_direct = registry.vector_store is vector_store

            # 3. Registry's EmbeddingService should be the same as Broker's
            es_shared = registry.embedding_service is broker.embedding_service

            return {
                "vs_shared_registry_broker": vs_shared_registry_broker,
                "vs_shared_registry_direct": vs_shared_registry_direct,
                "es_shared": es_shared,
            }

        client = TestClient(app)
        response = client.get("/test-graph")

        assert response.status_code == 200
        data = response.json()

        assert data["vs_shared_registry_broker"] is True
        assert data["vs_shared_registry_direct"] is True
        assert data["es_shared"] is True


def test_dependency_overrides() -> None:
    """
    Verify that FastAPI's dependency override mechanism works with the
    decorated singleton providers.
    """
    get_vector_store.cache_clear()  # type: ignore[attr-defined]

    app = FastAPI()

    @app.get("/test-override")  # type: ignore[misc]
    def check_override(
        vector_store: VectorStore = Depends(get_vector_store),  # noqa: B008
    ) -> dict[str, str]:
        return {"urn": "original"}

    client = TestClient(app)

    # 1. Test Original Behavior (init real/mocked original)
    with patch("coreason_catalog.services.vector_store.lancedb.connect") as mock_connect:
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.list_tables.return_value.tables = []

        response = client.get("/test-override")
        assert response.status_code == 200
        assert response.json() == {"urn": "original"}

    # 2. Test Override
    mock_override_vs = MagicMock(spec=VectorStore)

    app.dependency_overrides[get_vector_store] = lambda: mock_override_vs

    @app.get("/test-override-check")  # type: ignore[misc]
    def check_override_val(
        vector_store: VectorStore = Depends(get_vector_store),  # noqa: B008
    ) -> dict[str, bool]:
        return {"is_mock": vector_store is mock_override_vs}

    response = client.get("/test-override-check")
    assert response.status_code == 200
    assert response.json() == {"is_mock": True}


def test_retry_on_initialization_failure() -> None:
    """
    Verify that if singleton initialization fails, subsequent calls
    retry initialization instead of caching the failure.
    """
    get_vector_store.cache_clear()  # type: ignore[attr-defined]

    with patch("coreason_catalog.services.vector_store.lancedb.connect") as mock_connect:
        # First call: Fail
        mock_connect.side_effect = RuntimeError("Temporary Connection Failure")

        try:
            get_vector_store()
        except RuntimeError:
            pass
        else:
            pytest.fail("Should have raised RuntimeError")

        # Second call: Succeed
        mock_connect.side_effect = None
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        mock_db.list_tables.return_value.tables = []

        vs = get_vector_store()
        assert isinstance(vs, VectorStore)
        assert mock_connect.call_count == 2
