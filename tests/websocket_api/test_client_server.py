import pytest

from gptnt.websocket_api.client import WebsocketClient
from gptnt.websocket_api.server import WebsocketServer


@pytest.mark.asyncio
async def test_server_starts(host: str, port: int) -> None:
    async with WebsocketServer(host, port) as server:
        assert server.server is not None
        assert server.server.is_serving() is True


@pytest.mark.asyncio
async def test_client_init(host: str, port: int) -> None:
    client = WebsocketClient(host, port)
    assert client
    assert client.is_connected is False


@pytest.mark.asyncio
async def test_client_connects_to_server(host: str, port: int) -> None:
    async with WebsocketServer(host, port) as server, WebsocketClient(host, port) as client:
        assert server
        assert client
        assert client.is_connected is True

    # Ensure the client is no longer connected
    assert client.is_connected is False


@pytest.mark.asyncio
async def test_messages_works_across_websockets(host: str, port: int) -> None:
    """Ensure that messages can be sent and received correctly between a server and client."""
    async with WebsocketServer(host, port) as server, WebsocketClient(host, port) as client:
        server.on("test_endpoint_1", lambda _: "test_1")
        server.on("passthrough", lambda data: data)

        ep1_result = await client.send_request("test_endpoint_1", "")
        passthrough_result = await client.send_request("passthrough", data="passed through")

        assert ep1_result == "test_1"
        assert passthrough_result == "passed through"

    assert client.is_connected is False
