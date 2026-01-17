from fastapi import Depends, FastAPI, HTTPException
from starlette import status

from coreason_catalog.dependencies import get_federation_broker, get_registry_service
from coreason_catalog.models import CatalogResponse, QueryRequest, SourceManifest
from coreason_catalog.services.broker import FederationBroker
from coreason_catalog.services.registry import RegistryService
from coreason_catalog.utils.logger import logger

app = FastAPI(title="coreason-catalog", version="0.1.0")


@app.get("/health", response_model=dict[str, str])  # type: ignore[misc]
async def health_check() -> dict[str, str]:
    """
    Health check endpoint.
    """
    logger.info("Health check requested")
    return {"status": "ok"}


@app.post(
    "/v1/sources",
    status_code=status.HTTP_201_CREATED,
    response_model=dict[str, str],
)  # type: ignore[misc]
async def register_source(
    manifest: SourceManifest,
    registry_service: RegistryService = Depends(get_registry_service),  # noqa: B008
) -> dict[str, str]:
    """
    Register a new source manifest.
    """
    logger.info(f"Received registration request for source: {manifest.urn}")
    try:
        registry_service.register_source(manifest)
        return {"status": "registered", "urn": manifest.urn}
    except ValueError as e:
        logger.error(f"Validation error during registration: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
    except RuntimeError as e:
        logger.error(f"Runtime error during registration: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Unexpected error during registration: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error") from e


@app.post(
    "/v1/query",
    status_code=status.HTTP_200_OK,
    response_model=CatalogResponse,
)  # type: ignore[misc]
async def query_catalog(
    request: QueryRequest,
    broker: FederationBroker = Depends(get_federation_broker),  # noqa: B008
) -> CatalogResponse:
    """
    Query the catalog.
    """
    logger.info(f"Received query request: {request.intent}")
    try:
        response = await broker.dispatch_query(request.intent, request.user_context, request.limit)
        return response
    except Exception as e:
        logger.error(f"Unexpected error during query dispatch: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error") from e
