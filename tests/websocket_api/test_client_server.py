import pytest

from gptnt.websocket_api.client import WebsocketClient
from gptnt.websocket_api.server import WebsocketServer

TEST_HOST: str = "localhost"


# Server
def test_server_init() -> None:
    """Can server be initialised correctly."""
    test_port: int = 8080

    server = WebsocketServer(TEST_HOST, test_port)
    assert server


@pytest.mark.asyncio
async def test_server_start() -> None:
    """Can server be started correctly."""
    test_port: int = 8081

    async with WebsocketServer(TEST_HOST, test_port) as server:
        assert server


# Client
@pytest.mark.asyncio
async def test_client_init() -> None:
    """Can client be initialised correctly."""
    test_port: int = 8082

    client = WebsocketClient(TEST_HOST, test_port)
    assert client
    assert client.is_connected is False


@pytest.mark.asyncio
async def test_client_connect() -> None:
    """Can a client correctly connect to a server."""
    test_port: int = 8083

    async with (
        WebsocketServer(TEST_HOST, test_port) as server,
        WebsocketClient(TEST_HOST, test_port) as client,
    ):
        assert server
        assert client
        assert client.is_connected is True

    # Ensure the client is no longer connected
    assert client.is_connected is False


# Messaging
@pytest.mark.asyncio
async def test_websocket_messaging() -> None:
    """Can a server and client communicate correctly across multiple endpoints, and is data passed
    through the handlers correctly."""
    test_port: int = 8084

    async with (
        WebsocketServer(TEST_HOST, test_port) as server,
        WebsocketClient(TEST_HOST, test_port) as client,
    ):
        server.on("test_endpoint_1", lambda _: "test_1")
        server.on("passthrough", lambda data: data)

        ep1_result = await client.send_request("test_endpoint_1", "")
        passthrough_result = await client.send_request("passthrough", data="passed through")

        assert ep1_result == "test_1"
        assert passthrough_result == "passed through"

    assert client.is_connected is False
