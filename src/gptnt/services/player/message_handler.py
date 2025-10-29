from dataclasses import dataclass, field

import structlog
from faststream.redis import RedisBroker
from pydantic import UUID4, RedisDsn

from gptnt.players.actions import NO_NEW_MESSAGES_SENTINEL
from gptnt.players.specification import PlayerRole
from gptnt.services.broker import create_redis_broker
from gptnt.services.experiment_descriptor import ExperimentDescriptor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class MessageHandler:
    """Handle sending and receiving messages between players using Redis pub/sub.

    Each player subscribes to their own channel and publishes to other players' channels. Channel
    names are based on session_id and player role to ensure proper routing.
    """

    redis_url: RedisDsn = field(default=RedisDsn("redis://localhost:6379/0"))
    _broker: RedisBroker = field(init=False, repr=False)

    # Set during configuration
    session_id: UUID4 | None = field(default=None, init=False)
    my_role: PlayerRole | None = field(default=None, init=False)
    other_role: PlayerRole | None = field(default=None, init=False)

    # Internal state
    _unpulled_messages: list[str] = field(default_factory=list, init=False)
    _is_running: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Initialize FastStream Redis broker."""
        self._broker = create_redis_broker(self.redis_url)

    def configure_for_experiment(
        self, *, experiment_descriptor: ExperimentDescriptor, my_role: PlayerRole
    ) -> None:
        """Configure the message handler for a specific experiment.

        Args:
            experiment_descriptor: The experiment configuration
            my_role: This player's role ('defuser' or 'expert')
        """
        self.session_id = experiment_descriptor.session_id
        self.my_role = my_role
        self.other_role = "expert" if my_role == "defuser" else "defuser"

        logger.info(
            "Configured Redis message handler",
            session_id=self.session_id,
            my_role=self.my_role,
            other_role=self.other_role,
            my_channel=self._get_my_channel(),
            other_channel=self._get_other_channel(),
        )

    async def start_subscriber(self) -> None:
        """Start the Redis subscriber for this player's channel.

        This should be called when the experiment is configured and will run continuously until
        stop_subscriber() is called.
        """
        if self._is_running:
            logger.warning("Subscriber already running, skipping start")
            return

        channel = self._get_my_channel()
        _ = self._broker.subscriber(channel)(self.handle_new_message)

        # Start the broker in the background
        await self._broker.start()
        self._is_running = True
        logger.info("Started Redis message subscriber", channel=channel)

    async def stop_subscriber(self) -> None:
        """Stop the Redis subscriber.

        This should be called when the experiment ends or the player is reset.
        """
        if not self._is_running:
            return

        await self._broker.close()
        self._is_running = False
        logger.info("Stopped Redis message subscriber")

    async def send_message(self, message: str) -> None:
        """Send a message to the other player.

        This is non-blocking - it publishes to Redis and returns immediately without waiting for the other player to receive it.
        """
        channel = self._get_other_channel()

        # Note: if this fails, we will allow the exception since that's a big problem
        _ = await self._broker.publish(message, channel)

        logger.debug(
            "Published message", message=message, to_channel=channel, to_role=self.other_role
        )

    def pull_messages(self) -> str:
        """Pull all pending messages from the queue.

        Returns:
            A single string with all messages joined by newlines, or a sentinel value if no messages.
        """
        if not self._unpulled_messages:
            logger.debug("No new messages to pull")
            return NO_NEW_MESSAGES_SENTINEL

        # Join all messages and clear the queue
        messages = "\n".join(self._unpulled_messages)
        logger.debug("Pulled messages from queue", message_count=len(self._unpulled_messages))
        self._unpulled_messages.clear()

        return messages

    def handle_new_message(self, message: str) -> None:
        """Handle incoming messages."""
        self._unpulled_messages.append(message)
        logger.debug(
            "Received message ",
            message=message,
            channel=self._get_my_channel(),
            queue_size=len(self._unpulled_messages),
        )

    def reset(self) -> None:
        """Reset the message handler state."""
        self._unpulled_messages.clear()
        self.session_id = None
        self.my_role = None
        self.other_role = None
        logger.debug("Message handler reset")

    async def close(self) -> None:
        """Close Redis broker connection."""
        await self.stop_subscriber()
        logger.debug("Closed Redis broker")

    def _get_my_channel(self) -> str:
        """Get the channel name this player subscribes to."""
        if not self.session_id or not self.my_role:
            raise ValueError("Message handler not configured for experiment")
        return f"session:{self.session_id}:player:{self.my_role}:messages"

    def _get_other_channel(self) -> str:
        """Get the channel name to publish messages to the other player."""
        if not self.session_id or not self.other_role:
            raise ValueError("Message handler not configured for experiment")
        return f"session:{self.session_id}:player:{self.other_role}:messages"
