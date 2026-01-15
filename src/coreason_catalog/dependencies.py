# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_catalog

from threading import Lock
from typing import Callable, TypeVar

from fastapi import Depends

from coreason_catalog.services.broker import FederationBroker, QueryDispatcher
from coreason_catalog.services.embedding import EmbeddingService
from coreason_catalog.services.policy_engine import PolicyEngine
from coreason_catalog.services.provenance import ProvenanceService
from coreason_catalog.services.registry import RegistryService
from coreason_catalog.services.sse_dispatcher import SSEQueryDispatcher
from coreason_catalog.services.vector_store import VectorStore

T = TypeVar("T")


def thread_safe_singleton(func: Callable[[], T]) -> Callable[[], T]:
    """
    Decorator to ensure a function is called only once, thread-safely.
    Similar to lru_cache but with a Lock for strict concurrency safety on init.
    """
    lock = Lock()
    instance: T | None = None

    def wrapper() -> T:
        nonlocal instance
        if instance is None:
            with lock:
                if instance is None:
                    instance = func()
        return instance

    # Expose a way to clear the singleton for testing
    def cache_clear() -> None:
        nonlocal instance
        with lock:
            instance = None

    wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
    return wrapper


@thread_safe_singleton
def get_vector_store() -> VectorStore:
    """
    Singleton provider for VectorStore.
    """
    return VectorStore()


@thread_safe_singleton
def get_embedding_service() -> EmbeddingService:
    """
    Singleton provider for EmbeddingService.
    """
    return EmbeddingService()


@thread_safe_singleton
def get_policy_engine() -> PolicyEngine:
    """
    Singleton provider for PolicyEngine.
    """
    return PolicyEngine()


@thread_safe_singleton
def get_provenance_service() -> ProvenanceService:
    """
    Singleton provider for ProvenanceService.
    """
    return ProvenanceService()


@thread_safe_singleton
def get_query_dispatcher() -> QueryDispatcher:
    """
    Singleton provider for QueryDispatcher.
    """
    return SSEQueryDispatcher()


def get_registry_service(
    vector_store: VectorStore = Depends(get_vector_store),  # noqa: B008
    embedding_service: EmbeddingService = Depends(get_embedding_service),  # noqa: B008
) -> RegistryService:
    """
    Provider for RegistryService.
    """
    return RegistryService(vector_store, embedding_service)


def get_federation_broker(
    vector_store: VectorStore = Depends(get_vector_store),  # noqa: B008
    policy_engine: PolicyEngine = Depends(get_policy_engine),  # noqa: B008
    embedding_service: EmbeddingService = Depends(get_embedding_service),  # noqa: B008
    dispatcher: QueryDispatcher = Depends(get_query_dispatcher),  # noqa: B008
    provenance_service: ProvenanceService = Depends(get_provenance_service),  # noqa: B008
) -> FederationBroker:
    """
    Provider for FederationBroker.
    """
    return FederationBroker(
        vector_store=vector_store,
        policy_engine=policy_engine,
        embedding_service=embedding_service,
        dispatcher=dispatcher,
        provenance_service=provenance_service,
    )
