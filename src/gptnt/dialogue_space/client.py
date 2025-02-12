from uuid import uuid4

from gptnt.dialogue_space.structures import ClientRequest, SendMessageData
from gptnt.websocket_api.client import WebsocketClient


class DialogueSpaceClient:
    """Client connected to the dialogue-space."""

    def __init__(self, client: WebsocketClient) -> None:
        # Self-generate identifying uuid
        self.uuid = uuid4()

        # Client for connecting to dialogue-space
        self.client = client

    async def connect(self) -> None:
        """Conect agent to server, get UUID to self-identify."""
        _ = await self.client.connect()
        con_request = ClientRequest(uuid=self.uuid)
        _ = await self.client.send_request("connect", con_request.model_dump_json())

    async def send_message(self, message: str) -> None:
        """Send message to dialogue space."""
        message_request = SendMessageData(uuid=self.uuid, message=message)
        _ = await self.client.send_request("send_message", message_request.model_dump_json())

    async def pull_messages(self) -> list[str]:
        """Get unread messages from dialogue-space."""
        pull_request = ClientRequest(uuid=self.uuid)
        response = await self.client.send_request("pull_messages", pull_request.model_dump_json())
        return response
