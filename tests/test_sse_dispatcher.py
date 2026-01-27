import asyncio
from typing import Any, AsyncGenerator, List
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from coreason_catalog.models import DataSensitivity, SourceManifest
from coreason_catalog.services.sse_dispatcher import SSEQueryDispatcher


@pytest.fixture  # type: ignore[misc]
def mock_source() -> SourceManifest:
    return SourceManifest(
        urn="urn:coreason:mcp:test_source",
        name="Test Source",
        description="A test source",
        endpoint_url="sse://example.com/api/query",
        geo_location="US",
        sensitivity=DataSensitivity.PUBLIC,
        owner_group="TestGroup",
        access_policy="allow { true }",
    )


async def _async_gen(lines: List[str]) -> AsyncGenerator[str, None]:
    for line in lines:
        yield line


def create_mock_client(
    lines: List[str],
    status_code: int = 200,
    raise_http_error: bool = False,
    raise_network_error: bool = False,
    network_error_cls: Any = httpx.RequestError,
) -> MagicMock:
    """
    Helper to create a mock httpx.AsyncClient that simulates the stream context manager.
    """
    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_response = MagicMock(spec=httpx.Response)

    # Configure response behavior
    mock_response.status_code = status_code

    if raise_http_error:
        # Simulate raise_for_status raising an error
        error = httpx.HTTPStatusError(message="Error", request=MagicMock(), response=mock_response)
        mock_response.raise_for_status.side_effect = error
    else:
        mock_response.raise_for_status.return_value = None

    # Mock aiter_lines
    mock_response.aiter_lines.side_effect = lambda: _async_gen(lines)

    # Mock the async context manager for client.stream()
    async def mock_stream_context(*args: Any, **kwargs: Any) -> Any:
        if raise_network_error:
            raise network_error_cls("Network Error", request=MagicMock())
        return mock_response

    # We need __aenter__ to return the response mock
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(side_effect=mock_stream_context)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_client.stream.return_value = mock_context
    # Also mock aclose
    mock_client.aclose = AsyncMock()

    return mock_client


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_success(mock_source: SourceManifest) -> None:
    sse_content = [
        "event: message\n",
        'data: {"result": "part1"}\n',
        "\n",
        "event: message\n",
        'data: {"result": "part2"}\n',
        "\n",
    ]
    mock_client = create_mock_client(sse_content)
    dispatcher = SSEQueryDispatcher(client=mock_client)

    results = await dispatcher.dispatch(mock_source, "find data")

    assert len(results) == 2
    assert results[0] == {"result": "part1"}
    assert results[1] == {"result": "part2"}

    # Verify endpoint URL handling (sse:// -> http://)
    mock_client.stream.assert_called_with("POST", "http://example.com/api/query", json={"intent": "find data"})
    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_success_https() -> None:
    source = SourceManifest(
        urn="urn:coreason:mcp:test_source_secure",
        name="Test Source Secure",
        description="A test source",
        endpoint_url="sses://example.com/api/query",
        geo_location="US",
        sensitivity=DataSensitivity.PUBLIC,
        owner_group="TestGroup",
        access_policy="allow { true }",
    )
    sse_content = [
        "event: message\n",
        'data: {"result": "part1"}\n',
        "\n",
    ]
    mock_client = create_mock_client(sse_content)
    dispatcher = SSEQueryDispatcher(client=mock_client)

    results = await dispatcher.dispatch(source, "find data")

    assert len(results) == 1
    assert results[0] == {"result": "part1"}

    # Verify endpoint URL handling (sses:// -> https://)
    mock_client.stream.assert_called_with("POST", "https://example.com/api/query", json={"intent": "find data"})
    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_http_error(mock_source: SourceManifest) -> None:
    mock_client = create_mock_client([], status_code=500, raise_http_error=True)
    dispatcher = SSEQueryDispatcher(client=mock_client)

    with pytest.raises(httpx.HTTPStatusError):
        await dispatcher.dispatch(mock_source, "find data")

    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_network_error(mock_source: SourceManifest) -> None:
    mock_client = create_mock_client([], raise_network_error=True, network_error_cls=httpx.ConnectError)
    dispatcher = SSEQueryDispatcher(client=mock_client)

    with pytest.raises(httpx.RequestError):
        await dispatcher.dispatch(mock_source, "find data")

    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_malformed_json_and_empty_lines(mock_source: SourceManifest) -> None:
    sse_content = [
        'data: {"valid": true}\n',
        "\n",
        "data: \n",
        "\n",
        "data: INVALID_JSON\n",
        "\n",
    ]
    mock_client = create_mock_client(sse_content)
    dispatcher = SSEQueryDispatcher(client=mock_client)

    results = await dispatcher.dispatch(mock_source, "find data")

    # Should skip invalid JSON and empty lines
    assert len(results) == 1
    assert results[0] == {"valid": True}
    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_generic_exception(mock_source: SourceManifest) -> None:
    # Simulate generic exception during stream setup
    mock_client = MagicMock()
    mock_client.stream.side_effect = Exception("Generic Error")

    dispatcher = SSEQueryDispatcher(client=mock_client)

    with pytest.raises(Exception, match="Generic Error"):
        await dispatcher.dispatch(mock_source, "find data")


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_multiline_data(mock_source: SourceManifest) -> None:
    """Test handling of JSON split across multiple data lines."""
    # Ensure lines are simulated as yielding line-by-line including the final empty line
    sse_content = ["data: {\n", 'data: "key": "value",\n', 'data: "list": [1, 2, 3]\n', "data: }\n", "\n"]
    mock_client = create_mock_client(sse_content)
    dispatcher = SSEQueryDispatcher(client=mock_client)

    results = await dispatcher.dispatch(mock_source, "find data")

    assert len(results) == 1
    assert results[0] == {"key": "value", "list": [1, 2, 3]}
    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_ignored_fields(mock_source: SourceManifest) -> None:
    """Test that id, event, retry, and comments are ignored."""
    sse_content = [
        ": this is a comment\n",
        "id: 123\n",
        "event: update\n",
        "retry: 1000\n",
        'data: {"valid": true}\n',
        "\n",
        ": another comment\n",
    ]
    mock_client = create_mock_client(sse_content)
    dispatcher = SSEQueryDispatcher(client=mock_client)

    results = await dispatcher.dispatch(mock_source, "find data")

    assert len(results) == 1
    assert results[0] == {"valid": True}
    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_timeout(mock_source: SourceManifest) -> None:
    """Test that ReadTimeout is raised and handled."""
    mock_client = create_mock_client([], raise_network_error=True, network_error_cls=httpx.ReadTimeout)
    dispatcher = SSEQueryDispatcher(client=mock_client)

    with pytest.raises(httpx.RequestError):
        await dispatcher.dispatch(mock_source, "find data")

    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_concurrent(mock_source: SourceManifest) -> None:
    """Test concurrent dispatch calls."""
    # We need a fresh iterator for each call, create_mock_client handles this by lambda
    sse_content = ['data: {"result": "success"}\n', "\n"]
    mock_client = create_mock_client(sse_content)
    dispatcher = SSEQueryDispatcher(client=mock_client)

    tasks = [dispatcher.dispatch(mock_source, f"query {i}") for i in range(5)]
    results_list = await asyncio.gather(*tasks)

    assert len(results_list) == 5
    for results in results_list:
        assert results[0] == {"result": "success"}

    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_incomplete_stream(mock_source: SourceManifest) -> None:
    """Test handling of stream ending without final newline."""
    sse_content = ['data: {"result": "incomplete"}']
    mock_client = create_mock_client(sse_content)
    dispatcher = SSEQueryDispatcher(client=mock_client)

    results = await dispatcher.dispatch(mock_source, "find data")

    assert len(results) == 1
    assert results[0] == {"result": "incomplete"}
    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_incomplete_stream_invalid_json(mock_source: SourceManifest) -> None:
    """Test handling of stream ending without final newline AND invalid JSON."""
    sse_content = ["data: INVALID_JSON_AT_END"]
    mock_client = create_mock_client(sse_content)
    dispatcher = SSEQueryDispatcher(client=mock_client)

    results = await dispatcher.dispatch(mock_source, "find data")

    # Should handle exception and return empty list
    assert len(results) == 0
    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatcher_lifecycle() -> None:
    """Test that close() calls client.aclose() when client is owned."""
    # Patch httpx.AsyncClient at the module level where it is used
    with patch("coreason_catalog.services.sse_dispatcher.httpx.AsyncClient") as MockClientCls:
        mock_client_instance = AsyncMock()
        MockClientCls.return_value = mock_client_instance

        dispatcher = SSEQueryDispatcher()  # Should create its own client
        assert dispatcher._owns_client is True

        await dispatcher.close()

        mock_client_instance.aclose.assert_awaited_once()

    # Test when client is NOT owned
    mock_shared_client = AsyncMock()
    dispatcher_shared = SSEQueryDispatcher(client=mock_shared_client)
    assert dispatcher_shared._owns_client is False

    await dispatcher_shared.close()
    mock_shared_client.aclose.assert_not_awaited()
