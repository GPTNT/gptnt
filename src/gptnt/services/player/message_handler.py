from dataclasses import dataclass, field

import logfire
import structlog

from gptnt.common.base_client import BaseClient
from gptnt.players.actions import NO_NEW_MESSAGES_SENTINEL

logger = structlog.get_logger()


@dataclass(kw_only=True)
class MessageManager(BaseClient):
    """Handle sending messages to players and process messages from players."""

    _unpulled_messages: list[str] = field(default_factory=list, init=False)

    @logfire.instrument("Receive message")
    def handle_new_message(self, message: str) -> None:
        """Handler for new (dialogue) messages."""
        self._unpulled_messages.append(message)
        logger.debug("Received message", message=message)

    @logfire.instrument("Send message")
    async def send_message(self, message: str) -> None:
        """Send a message to the other player."""
        logger.debug("Sending message", message=message)
        response = await self.client.post("/send-message", json={"message": message})
        _ = response.raise_for_status()
        logger.debug("Message sent successfully", message=message)

    def pull_messages(self) -> str:
        """Pull messages from the queue.

        If there are several, we return a join of them. If there are none, we return the default
        sentinel.
        """
        if not self._unpulled_messages:
            logger.debug("No new messages to pull.")
            return NO_NEW_MESSAGES_SENTINEL

        # Flatten the messages into a single string
        new_messages = "\n".join(self._unpulled_messages)
        self._unpulled_messages.clear()
        return new_messages

    def reset(self) -> None:
        """Reset the message handler."""
        _ = self.clear_client_url()
        self._unpulled_messages.clear()
        logger.debug("Message handler reset, cleared unpulled messages.")
