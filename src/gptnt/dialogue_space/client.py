from types import TracebackType
from typing import Self
from uuid import uuid4

import logfire
from httpx import URL

from gptnt.dialogue_space.structures import ClientRequest, SendMessageData
from gptnt.websocket_api.client import WebsocketClient


class DialogueSpaceClient:
    """Client connected to the dialogue-space."""

    def __init__(self, client: WebsocketClient) -> None:
        # Self-generate identifying uuid
        self.uuid = uuid4()

        # Client for connecting to dialogue-space
        self.client = client

    @classmethod
    def from_host_and_port(cls, host: str, port: int) -> Self:
        """Initialise dialogue space client with host and port, using Websockets."""
        client = WebsocketClient(host=host, port=port)
        return cls(client=client)

    @classmethod
    def from_url(cls, url: str) -> Self:
        """Initialise dialogue space client with URL, using Websockets."""
        parsed_url = URL(url)
        assert parsed_url.port is not None, "URL must include port"

        client = WebsocketClient(host=parsed_url.host, port=parsed_url.port)
        return cls(client=client)

    async def __aenter__(self) -> Self:
        """Enter async context manager."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        """Exit async context manager."""
        await self.disconnect()

    @property
    def is_connected(self) -> bool:
        """Check if client is connected to server."""
        return self.client.is_connected

    @logfire.instrument("Connect to dialogue space")
    async def connect(self) -> None:
        """Connect agent to server, get UUID to self-identify."""
        _ = await self.client.connect()
        con_request = ClientRequest(uuid=self.uuid)
        _ = await self.client.send_request("connect", con_request.model_dump_json())

    async def disconnect(self) -> None:
        """Disconnect agent from server."""
        await self.client.__aexit__()

    @logfire.instrument("Send message to dialogue space")
    async def send_message(self, message: str) -> None:
        """Send message to dialogue space."""
        message_request = SendMessageData(uuid=self.uuid, message=message)
        _ = await self.client.send_request("send_message", message_request.model_dump_json())

    @logfire.instrument("Pull messages from dialogue space")
    async def pull_messages(self) -> list[str]:
        """Get unread messages from dialogue-space."""
        pull_request = ClientRequest(uuid=self.uuid)
        response = await self.client.send_request("pull_messages", pull_request.model_dump_json())
        return response
