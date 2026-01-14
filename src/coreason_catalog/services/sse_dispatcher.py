import json
from typing import Any, List, Optional

import httpx
from coreason_catalog.models import SourceManifest
from coreason_catalog.services.broker import QueryDispatcher
from coreason_catalog.utils.logger import logger


class SSEQueryDispatcher(QueryDispatcher):
    """
    Concrete implementation of QueryDispatcher using Server-Sent Events (SSE).
    """

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        """
        Initialize the SSEQueryDispatcher.

        Args:
            client: Optional shared httpx.AsyncClient.
        """
        self.client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def dispatch(self, source: SourceManifest, intent: str) -> Any:
        """
        Dispatch the intent to the source via SSE.

        Args:
            source: The target source manifest.
            intent: The intent string.

        Returns:
            The aggregated data from the SSE stream.
        """
        url = source.endpoint_url
        if url.startswith("sse://"):
            url = "http" + url[3:]
        elif url.startswith("sses://"):
            url = "https" + url[4:]

        logger.info(f"Dispatching to {url} with intent: {intent}")

        try:
            # We assume the intent is sent as a JSON body in a POST request.
            # The server responds with an SSE stream.
            async with self.client.stream("POST", url, json={"intent": intent}) as response:
                response.raise_for_status()

                results: List[Any] = []
                buffer: List[str] = []

                async for line in response.aiter_lines():
                    # Check for empty line (Event Separator)
                    if not line.strip():
                        if buffer:
                            # Process buffered data
                            full_data = "".join(buffer)
                            buffer = []  # Reset buffer
                            try:
                                data = json.loads(full_data)
                                results.append(data)
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse SSE data from {source.urn}: {full_data}")
                        continue

                    if line.startswith("data:"):
                        # SSE spec says remove "data:" prefix.
                        # If there is a space after colon, remove it too.
                        content = line[5:]
                        if content.startswith(" "):
                            content = content[1:]

                        buffer.append(content)

                    # We ignore 'id:', 'event:', 'retry:', and comments (starting with ':')
                    # for the MVP. If specific event types are needed, we can add logic here.

                # Handle case where stream ends without a final newline (flush buffer)
                if buffer:
                    full_data = "".join(buffer)
                    try:
                        data = json.loads(full_data)
                        results.append(data)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse SSE data from {source.urn}: {full_data}")

                return results

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code} dispatching to {source.urn}: {e}")
            raise e
        except httpx.RequestError as e:
            logger.error(f"Network error dispatching to {source.urn}: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error dispatching to {source.urn}: {e}")
            raise e

    async def close(self) -> None:
        """Close the underlying client if owned."""
        if self._owns_client:
            await self.client.aclose()
