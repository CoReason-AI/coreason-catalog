import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from coreason_catalog.models import CatalogResponse, SourceManifest, SourceResult
from coreason_catalog.services.embedding import EmbeddingService
from coreason_catalog.services.policy_engine import PolicyEngine
from coreason_catalog.services.provenance import ProvenanceService
from coreason_catalog.services.vector_store import VectorStore
from coreason_catalog.utils.logger import logger


class QueryDispatcher(ABC):
    """
    Abstract interface for dispatching queries to MCP servers.
    """

    @abstractmethod
    async def dispatch(self, source: SourceManifest, intent: str) -> Any:
        """
        Dispatch the intent to the specific source.

        Args:
            source: The target source manifest.
            intent: The natural language intent or query.

        Returns:
            The raw data returned by the source.
        """
        pass  # pragma: no cover


class FederationBroker:
    """
    The Cartographer and Router.
    Orchestrates Discovery, Governance, Dispatch, and Aggregation.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        policy_engine: PolicyEngine,
        embedding_service: EmbeddingService,
        dispatcher: QueryDispatcher,
        provenance_service: ProvenanceService,
    ):
        self.vector_store = vector_store
        self.policy_engine = policy_engine
        self.embedding_service = embedding_service
        self.dispatcher = dispatcher
        self.provenance_service = provenance_service

    async def dispatch_query(self, intent: str, user_context: Dict[str, Any], limit: int = 10) -> CatalogResponse:
        """
        Execute the Register-Discover-Govern-Stamp Loop.

        1. Semantic Discovery: Find sources matching the intent.
        2. Governance: Filter sources based on policy and user context.
        3. Dispatch: Query allowed sources in parallel.
        4. Aggregation: Combine results and stamp with provenance.

        Args:
            intent: The user's high-level query/intent.
            user_context: The user/agent context (Subject) for policy evaluation.
            limit: Max number of sources to query.

        Returns:
            A CatalogResponse containing aggregated results.
        """
        query_id = uuid.uuid4()
        logger.info(f"Processing query {query_id}: '{intent}'", user=user_context.get("user_id"))

        # 1. Semantic Discovery
        # Embed the intent
        try:
            intent_embedding = self.embedding_service.embed_text(intent)
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            # If embedding fails, we can't search. Return empty response or error.
            # For now, let's return an empty response with no results.
            return CatalogResponse(
                query_id=query_id, aggregated_results=[], provenance_signature="ERROR: Embedding Failed"
            )

        # Search Vector Store
        try:
            candidates = self.vector_store.search(intent_embedding, limit=limit)
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return CatalogResponse(
                query_id=query_id, aggregated_results=[], provenance_signature="ERROR: Search Failed"
            )

        logger.info(f"Found {len(candidates)} candidate sources.")

        # 2. Governance (Policy Filtering)
        allowed_sources: List[SourceManifest] = []
        for source in candidates:
            # Construct Input Context for OPA
            # Subject: user_context
            # Object: source attributes
            # Action: "QUERY"
            input_data = {
                "subject": user_context,
                "object": {
                    "urn": source.urn,
                    "geo": source.geo_location,
                    "sensitivity": source.sensitivity.value,
                    "owner": source.owner_group,
                },
                "action": "QUERY",
            }

            try:
                # evaluate_policy uses subprocess, so it blocks.
                # Ideally, offload to thread, but keeping simple for now.
                is_allowed = self.policy_engine.evaluate_policy(source.access_policy, input_data)
                if is_allowed:
                    allowed_sources.append(source)
                else:
                    logger.info(f"Source {source.urn} blocked by policy.")
                    # We might want to record blocked attempts in the future (Story B)
            except Exception as e:
                logger.error(f"Policy evaluation failed for {source.urn}: {e}")
                # Fail closed: if policy fails, assume blocked.
                continue

        logger.info(f"Allowed {len(allowed_sources)} sources after governance check.")

        # 3. Dispatch & 4. Aggregation
        results: List[SourceResult] = []

        if not allowed_sources:
            return CatalogResponse(
                query_id=query_id,
                aggregated_results=[],
                provenance_signature=self.provenance_service.generate_provenance(query_id, []),
            )

        # Define an async worker for dispatching
        async def query_source(source: SourceManifest) -> SourceResult:
            start_time = time.time()
            try:
                data = await self.dispatcher.dispatch(source, intent)
                latency = (time.time() - start_time) * 1000
                return SourceResult(source_urn=source.urn, status="SUCCESS", data=data, latency_ms=latency)
            except Exception as e:
                latency = (time.time() - start_time) * 1000
                logger.error(f"Query to {source.urn} failed: {e}")
                return SourceResult(
                    source_urn=source.urn,
                    status="ERROR",
                    data={"error": str(e)},
                    latency_ms=latency,
                )

        # Run all queries in parallel
        tasks = [query_source(s) for s in allowed_sources]
        results = await asyncio.gather(*tasks)

        # Final Response
        response = CatalogResponse(
            query_id=query_id,
            aggregated_results=list(results),
            provenance_signature=self.provenance_service.generate_provenance(query_id, list(results)),
        )

        return response
