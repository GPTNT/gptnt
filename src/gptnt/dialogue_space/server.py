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

_logger = getLogger()


class DialogueSpaceServer:
    """Dialogue space."""

    def __init__(self, server: WebsocketServer) -> None:
        # Datastore structures
        self.agents: dict[UUID, DialogueSpaceAgent] = {}
        self.messages: list[DialogueSpaceMessage] = []

        # Server for client connectivity
        self.server = server

    async def __aenter__(self) -> Self:
        """Start dialogue space server and register endpoint callbacks."""
        _ = await self.server.start()
        self.server.on("connect", callback=self._on_agent_connect_req)
        self.server.on("send_message", callback=self._on_message_sent)
        self.server.on("pull_messages", callback=self._on_pull_messages)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        """Safe async context exiting logic."""
        # Empty agents store once server has stopped
        self.agents.clear()
        await self.server.stop()

    def add_message(self, sender_uuid: UUID, message: str) -> int:
        """Append message to datastore.

        Returns ID of most recent message.
        """
        new_id = self._get_highest_message_id() + 1
        new_message = DialogueSpaceMessage(
            sender_uuid=sender_uuid, message_id=new_id, message_content=message
        )
        self.messages.append(new_message)
        return new_id

    def get_unread_messages(self, agent_id: UUID) -> list[DialogueSpaceMessage]:
        """Return list of messages with id greater than agent's last read message ID."""
        agent = self.agents[agent_id]

        # Store agents last read message for return
        last_read_id = agent.last_read_message
        _logger.info(f"Last read message id: {last_read_id}")

        # Set last read to most recent message
        agent.last_read_message = self._get_highest_message_id()
        _logger.info(f"Set {agent.uuid} agent's last read message to {agent.last_read_message}")

        # Send all messages since last read
        return [message for message in self.messages if message.message_id > last_read_id]

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

    def _on_agent_connect_req(self, data: str) -> None:
        """Called when agent connects to dialogue-space."""
        parsed = ClientRequest.model_validate_json(data)
        _logger.info(f"Received connection from: {parsed.uuid}")
        agent_id = parsed.uuid
        new_agent = DialogueSpaceAgent(uuid=agent_id)
        self.agents[agent_id] = new_agent  # Store agent

    def _get_highest_message_id(self) -> int:
        if not self.messages:
            return -1  # Check list is empty
        return max(message.message_id for message in self.messages)
