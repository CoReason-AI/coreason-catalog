import httpx
import pytest
import respx
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
        "data: \n\n",  # Empty data (keep-alive)
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

    # We'll use a mocked client for this one to force the exception more easily
    # without relying on respx for everything.

    mock_client = httpx.AsyncClient()
    # Mocking stream context manager is a bit complex, let's stick to respx if possible
    # or just use unittest.mock on the client passed in.

    import unittest.mock

    mock_client.stream = unittest.mock.MagicMock(side_effect=Exception("Generic Error"))

    dispatcher_with_mock = SSEQueryDispatcher(client=mock_client)

    with pytest.raises(Exception, match="Generic Error"):
        await dispatcher_with_mock.dispatch(mock_source, "find data")
