import itertools
from types import TracebackType
from typing import Self
from uuid import UUID

from structlog import getLogger

from gptnt.dialogue_space.structures import (
    ClientRequest,
    DialogueSpaceAgent,
    DialogueSpaceMessage,
    SendMessageData,
)
from gptnt.websocket_api.server import WebsocketServer

log = getLogger()


class DialogueSpaceServer:
    """Dialogue space."""

    def __init__(self, server: WebsocketServer) -> None:
        # Datastore structures
        self.agents: dict[UUID, DialogueSpaceAgent] = {}
        self.messages: dict[int, DialogueSpaceMessage] = {}

        # Server for client connectivity
        self.server = server

    @classmethod
    def from_host_and_port(cls, host: str, port: int) -> Self:
        """Initialise dialogue space server with host and port, using Websockets."""
        server = WebsocketServer(host=host, port=port)
        return cls(server=server)

    @property
    def url(self) -> str:
        """Get the URL of the dialogue space server."""
        return f"ws://{self.host}:{self.port}"

    @property
    def host(self) -> str:
        """Get the host of the dialogue space server."""
        return self.server.host

    @property
    def port(self) -> int:
        """Get the port of the dialogue space server."""
        return self.server.port

    @property
    def active_connections(self) -> int:
        """Get the number of active connections."""
        if self.server.server is None:
            return 0
        return len(self.server.server.connections)

    async def start(self) -> Self:
        """Start the dialogue space server."""
        _ = await self.connect()
        return self

    async def close(self) -> None:
        """Close the dialogue space server."""
        await self.server.stop()
        # Empty agents store once server has stopped
        self.agents.clear()

    async def __aenter__(self) -> Self:
        """Start dialogue space server and register endpoint callbacks."""
        return await self.start()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        """Close dialogue space server."""
        await self.close()

    async def connect(self) -> None:
        """Start the dialogue space server and register endpoint callbacks."""
        _ = await self.server.start()
        self.server.on("connect", callback=self._on_agent_connect_request)
        self.server.on("send_message", callback=self._on_message_sent)
        self.server.on("pull_messages", callback=self._on_pull_messages)

    def reset(self) -> None:
        """Reset the dialogue space server."""
        self.agents = {}
        self.messages = {}

    @property
    def next_message_id(self) -> int:
        """Get the highest message ID in the datastore."""
        return len(self.messages)

    def add_message(self, sender_uuid: UUID, message: str) -> int:
        """Append message to datastore.

        Returns ID of most recent message.
        """
        if self.next_message_id in self.messages:
            raise ValueError(f"Message with ID {self.next_message_id} already exists.")

        new_message = DialogueSpaceMessage(
            sender_uuid=sender_uuid, message_id=self.next_message_id, message_content=message
        )
        self.messages[self.next_message_id] = new_message

        log.debug(f"Added message with ID {self.next_message_id}")
        return self.next_message_id

    def get_unread_messages(self, agent_id: UUID) -> list[DialogueSpaceMessage]:
        """Return list of messages with id greater than agent's last read message ID."""
        agent = self.agents[agent_id]

        # Get the new last read message ID for the agent
        latest_message_id = self.next_message_id - 1

        # We slice all the messages between two points
        messages_since_last_read = itertools.islice(
            self.messages.values(), agent.last_read_message_id + 1, latest_message_id + 1
        )
        # Filter out messages that should not be pulled by the agent (i.e. ones from itself)
        messages_since_last_read = (
            message for message in messages_since_last_read if message.sender_uuid != agent_id
        )
        messages_since_last_read = list(messages_since_last_read)

        # Set last read to most recent message
        agent.last_read_message_id = latest_message_id

        return messages_since_last_read

    def _on_pull_messages(self, data: str) -> list[str]:
        parsed = ClientRequest.model_validate_json(data)
        agent_id = parsed.uuid
        unread_messages = self.get_unread_messages(agent_id)
        return [
            message.message_content for message in unread_messages
        ]  # TODO: Do we want additional data per each message or just raw content?

    def _on_message_sent(self, data: str) -> None:
        parsed = SendMessageData.model_validate_json(data)
        _ = self.add_message(parsed.uuid, parsed.message)
        log.info(f"Message received: {parsed.message}")

    def _on_agent_connect_request(self, data: str) -> None:
        """Handle when an agent wants to connect to the server."""
        parsed = ClientRequest.model_validate_json(data)
        log.info(f"Received connection from {parsed.uuid}")

        if parsed.uuid in self.agents:
            raise ValueError(f"Agent with UUID {parsed.uuid} already connected.")

        self.agents[parsed.uuid] = DialogueSpaceAgent(uuid=parsed.uuid)
