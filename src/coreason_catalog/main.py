from fastapi import FastAPI

from coreason_catalog.utils.logger import logger

app = FastAPI(title="coreason-catalog", version="0.1.0")


@app.get("/health", response_model=dict[str, str])  # type: ignore[misc]
async def health_check() -> dict[str, str]:
    """
    Health check endpoint.
    """
    logger.info("Health check requested")
    return {"status": "ok"}
