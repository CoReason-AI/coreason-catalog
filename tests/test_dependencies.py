# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_catalog

from unittest.mock import MagicMock, patch

from coreason_catalog.dependencies import (
    get_embedding_service,
    get_federation_broker,
    get_policy_engine,
    get_provenance_service,
    get_query_dispatcher,
    get_registry_service,
    get_vector_store,
)
from coreason_catalog.services.broker import FederationBroker
from coreason_catalog.services.embedding import EmbeddingService
from coreason_catalog.services.policy_engine import PolicyEngine
from coreason_catalog.services.provenance import ProvenanceService
from coreason_catalog.services.registry import RegistryService
from coreason_catalog.services.sse_dispatcher import SSEQueryDispatcher
from coreason_catalog.services.vector_store import VectorStore


def test_get_vector_store_singleton() -> None:
    with patch("coreason_catalog.services.vector_store.lancedb.connect") as mock_connect:
        # Mock the db object returned by connect
        mock_db = MagicMock()
        mock_connect.return_value = mock_db
        # Mock list_tables to avoid further interaction
        mock_db.list_tables.return_value.tables = []

        # Clear cache first to ensure we hit the mock
        get_vector_store.cache_clear()  # type: ignore[attr-defined]

        vs1 = get_vector_store()
        vs2 = get_vector_store()

        assert isinstance(vs1, VectorStore)
        assert vs1 is vs2
        mock_connect.assert_called_once()


def test_get_embedding_service_singleton() -> None:
    with patch("coreason_catalog.services.embedding.TextEmbedding") as mock_embed:
        get_embedding_service.cache_clear()  # type: ignore[attr-defined]

        es1 = get_embedding_service()
        es2 = get_embedding_service()

        assert isinstance(es1, EmbeddingService)
        assert es1 is es2
        mock_embed.assert_called_once()


def test_get_policy_engine_singleton() -> None:
    with patch("coreason_catalog.services.policy_engine.shutil.which") as mock_which:
        mock_which.return_value = "/bin/opa"
        get_policy_engine.cache_clear()  # type: ignore[attr-defined]

        pe1 = get_policy_engine()
        pe2 = get_policy_engine()

        assert isinstance(pe1, PolicyEngine)
        assert pe1 is pe2


def test_get_provenance_service_singleton() -> None:
    get_provenance_service.cache_clear()  # type: ignore[attr-defined]

    ps1 = get_provenance_service()
    ps2 = get_provenance_service()

    assert isinstance(ps1, ProvenanceService)
    assert ps1 is ps2


def test_get_query_dispatcher_singleton() -> None:
    get_query_dispatcher.cache_clear()  # type: ignore[attr-defined]

    qd1 = get_query_dispatcher()
    qd2 = get_query_dispatcher()

    assert isinstance(qd1, SSEQueryDispatcher)
    assert qd1 is qd2


def test_get_registry_service() -> None:
    mock_vs = MagicMock(spec=VectorStore)
    mock_es = MagicMock(spec=EmbeddingService)

    rs = get_registry_service(mock_vs, mock_es)

    assert isinstance(rs, RegistryService)
    assert rs.vector_store is mock_vs
    assert rs.embedding_service is mock_es


def test_get_federation_broker() -> None:
    mock_vs = MagicMock(spec=VectorStore)
    mock_pe = MagicMock(spec=PolicyEngine)
    mock_es = MagicMock(spec=EmbeddingService)
    mock_qd = MagicMock(spec=SSEQueryDispatcher)
    mock_ps = MagicMock(spec=ProvenanceService)

    fb = get_federation_broker(mock_vs, mock_pe, mock_es, mock_qd, mock_ps)

    assert isinstance(fb, FederationBroker)
    assert fb.vector_store is mock_vs
    assert fb.policy_engine is mock_pe
    assert fb.embedding_service is mock_es
    assert fb.dispatcher is mock_qd
    assert fb.provenance_service is mock_ps
