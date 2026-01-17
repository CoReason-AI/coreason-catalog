import asyncio

import httpx
import pytest
from coreason_catalog.models import DataSensitivity, SourceManifest
from coreason_catalog.services.sse_dispatcher import SSEQueryDispatcher

# Check for respx module
respx = pytest.importorskip("respx")


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


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_success(mock_source: SourceManifest) -> None:
    dispatcher = SSEQueryDispatcher()

    # Mock the SSE response
    sse_content = [
        "event: message\n",
        'data: {"result": "part1"}\n\n',
        "event: message\n",
        'data: {"result": "part2"}\n\n',
    ]

    async with respx.mock(base_url="http://example.com") as respx_mock:
        route = respx_mock.post("/api/query").respond(
            status_code=200,
            content="".join(sse_content),
            headers={"Content-Type": "text/event-stream"},
        )

        results = await dispatcher.dispatch(mock_source, "find data")

        assert route.called
        assert len(results) == 2
        assert results[0] == {"result": "part1"}
        assert results[1] == {"result": "part2"}

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
    dispatcher = SSEQueryDispatcher()

    # Mock the SSE response
    sse_content = [
        "event: message\n",
        'data: {"result": "part1"}\n\n',
    ]

    async with respx.mock(base_url="https://example.com") as respx_mock:
        route = respx_mock.post("/api/query").respond(
            status_code=200,
            content="".join(sse_content),
            headers={"Content-Type": "text/event-stream"},
        )

        results = await dispatcher.dispatch(source, "find data")

        assert route.called
        assert len(results) == 1
        assert results[0] == {"result": "part1"}

    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_http_error(mock_source: SourceManifest) -> None:
    dispatcher = SSEQueryDispatcher()

    async with respx.mock(base_url="http://example.com") as respx_mock:
        respx_mock.post("/api/query").respond(status_code=500)

        with pytest.raises(httpx.HTTPStatusError):
            await dispatcher.dispatch(mock_source, "find data")

    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_network_error(mock_source: SourceManifest) -> None:
    dispatcher = SSEQueryDispatcher()

    async with respx.mock(base_url="http://example.com") as respx_mock:
        respx_mock.post("/api/query").mock(side_effect=httpx.ConnectError("Connection failed"))

        with pytest.raises(httpx.RequestError):
            await dispatcher.dispatch(mock_source, "find data")

    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_malformed_json_and_empty_lines(mock_source: SourceManifest) -> None:
    dispatcher = SSEQueryDispatcher()

    sse_content = [
        'data: {"valid": true}\n\n',
        "data: \n\n",  # Empty data (keep-alive) - handled by buffer reset/empty check logic
        "data: INVALID_JSON\n\n",
    ]

    async with respx.mock(base_url="http://example.com") as respx_mock:
        respx_mock.post("/api/query").respond(
            status_code=200,
            content="".join(sse_content),
            headers={"Content-Type": "text/event-stream"},
        )

        results = await dispatcher.dispatch(mock_source, "find data")

        # Should skip invalid JSON and empty lines
        assert len(results) == 1
        assert results[0] == {"valid": True}

    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_generic_exception(mock_source: SourceManifest) -> None:
    # To test generic exception, we can mock something that raises a non-httpx exception
    # Or mock the 'stream' method on the client to raise Exception

    mock_client = httpx.AsyncClient()

    import unittest.mock

    mock_client.stream = unittest.mock.MagicMock(side_effect=Exception("Generic Error"))

    dispatcher_with_mock = SSEQueryDispatcher(client=mock_client)

    with pytest.raises(Exception, match="Generic Error"):
        await dispatcher_with_mock.dispatch(mock_source, "find data")


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_multiline_data(mock_source: SourceManifest) -> None:
    """Test handling of JSON split across multiple data lines."""
    dispatcher = SSEQueryDispatcher()

    sse_content = ["data: {\n", 'data: "key": "value",\n', 'data: "list": [1, 2, 3]\n', "data: }\n\n"]

    async with respx.mock(base_url="http://example.com") as respx_mock:
        respx_mock.post("/api/query").respond(
            status_code=200,
            content="".join(sse_content),
            headers={"Content-Type": "text/event-stream"},
        )

        results = await dispatcher.dispatch(mock_source, "find data")

        assert len(results) == 1
        assert results[0] == {"key": "value", "list": [1, 2, 3]}

    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_ignored_fields(mock_source: SourceManifest) -> None:
    """Test that id, event, retry, and comments are ignored."""
    dispatcher = SSEQueryDispatcher()

    sse_content = [
        ": this is a comment\n",
        "id: 123\n",
        "event: update\n",
        "retry: 1000\n",
        'data: {"valid": true}\n\n',
        ": another comment\n",
    ]

    async with respx.mock(base_url="http://example.com") as respx_mock:
        respx_mock.post("/api/query").respond(
            status_code=200,
            content="".join(sse_content),
            headers={"Content-Type": "text/event-stream"},
        )

        results = await dispatcher.dispatch(mock_source, "find data")

        assert len(results) == 1
        assert results[0] == {"valid": True}

    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_timeout(mock_source: SourceManifest) -> None:
    """Test that ReadTimeout is raised and handled."""
    dispatcher = SSEQueryDispatcher(client=httpx.AsyncClient(timeout=0.1))

    async with respx.mock(base_url="http://example.com") as respx_mock:
        # Mock a route that sleeps longer than the timeout
        respx_mock.post("/api/query").mock(side_effect=httpx.ReadTimeout("Timeout"))

        with pytest.raises(httpx.RequestError):  # ReadTimeout is a RequestError
            await dispatcher.dispatch(mock_source, "find data")

    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_concurrent(mock_source: SourceManifest) -> None:
    """Test concurrent dispatch calls."""
    dispatcher = SSEQueryDispatcher()

    sse_content = 'data: {"result": "success"}\n\n'

    async with respx.mock(base_url="http://example.com") as respx_mock:
        respx_mock.post("/api/query").respond(
            status_code=200,
            content=sse_content,
            headers={"Content-Type": "text/event-stream"},
        )

        tasks = [dispatcher.dispatch(mock_source, f"query {i}") for i in range(5)]
        results_list = await asyncio.gather(*tasks)

        assert len(results_list) == 5
        for results in results_list:
            assert results[0] == {"result": "success"}

    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_incomplete_stream(mock_source: SourceManifest) -> None:
    """Test handling of stream ending without final newline."""
    dispatcher = SSEQueryDispatcher()

    # Stream ends abruptly after data
    sse_content = 'data: {"result": "incomplete"}'

    async with respx.mock(base_url="http://example.com") as respx_mock:
        respx_mock.post("/api/query").respond(
            status_code=200,
            content=sse_content,
            headers={"Content-Type": "text/event-stream"},
        )

        results = await dispatcher.dispatch(mock_source, "find data")

        assert len(results) == 1
        assert results[0] == {"result": "incomplete"}

    await dispatcher.close()


@pytest.mark.asyncio  # type: ignore[misc]
async def test_sse_dispatch_incomplete_stream_invalid_json(mock_source: SourceManifest) -> None:
    """Test handling of stream ending without final newline AND invalid JSON."""
    dispatcher = SSEQueryDispatcher()

    # Stream ends abruptly after invalid data
    sse_content = "data: INVALID_JSON_AT_END"

    async with respx.mock(base_url="http://example.com") as respx_mock:
        respx_mock.post("/api/query").respond(
            status_code=200,
            content=sse_content,
            headers={"Content-Type": "text/event-stream"},
        )

        results = await dispatcher.dispatch(mock_source, "find data")

        # Should handle exception and return empty list
        assert len(results) == 0

    await dispatcher.close()
