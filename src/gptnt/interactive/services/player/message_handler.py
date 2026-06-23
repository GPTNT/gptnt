from dataclasses import dataclass, field

import structlog
from faststream.redis import RedisBroker
from faststream.redis.subscriber.usecases import ChannelSubscriber
from pydantic import UUID4

from gptnt.experiments.descriptor import ExperimentDescriptor
from gptnt.players.actions import NO_NEW_MESSAGES_SENTINEL
from gptnt.specification import PlayerRole

logger = structlog.get_logger()


@dataclass(kw_only=True)
class IncomingMessageHandler:
    """Handle sending and receiving messages between players using Redis pub/sub.

    Each player subscribes to their own channel and publishes to other players' channels. Channel
    names are based on session_id and player role to ensure proper routing.
    """

    broker: RedisBroker

    # Set during configuration
    session_id: UUID4 | None = field(default=None, init=False)
    my_role: PlayerRole | None = field(default=None, init=False)
    other_role: PlayerRole | None = field(default=None, init=False)

    # Internal state
    _subscriber: ChannelSubscriber | None = field(default=None, init=False, repr=False)
    _unpulled_messages: list[str] = field(default_factory=list, init=False)
    _unpulled_feedback: list[str] = field(default_factory=list, init=False)

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

        Note: The broker is already started and managed by FastStream. We just register
        the subscriber here.
        """
        if self._is_running:
            logger.warning("Subscriber already running, skipping start")
            return

        channel = self._get_my_channel()
        self._subscriber = self.broker.subscriber(channel)
        _ = self._subscriber(self.handle_new_message)
        await self._subscriber.start()

        logger.info("Registered Redis message subscriber", channel=channel)

    async def stop_subscriber(self) -> None:
        """Stop the Redis subscriber.

        This should be called when the experiment ends or the player is reset.

        Note: We don't close the broker since it's shared and managed by FastStream.
        We just unregister by marking as not running.
        """
        if not self._is_running or self._subscriber is None:
            return

        await self._subscriber.stop()
        self._subscriber = None
        logger.info("Stopped Redis message subscriber")

    async def send_message(self, message: str) -> None:
        """Send a message to the other player.

        This is non-blocking - it publishes to Redis and returns immediately without waiting for
        the other player to receive it.
        """
        channel = self._get_other_channel()

        # Note: if this fails, we will allow the exception since that's a big problem
        _ = await self.broker.publish(message, channel)

        logger.debug(
            "Published message", message=message, to_channel=channel, to_role=self.other_role
        )

    def pull_messages(self) -> str:
        """Pull all pending messages from the queue.

        Returns:
            A single string with all pending feedback and normal messages joined by
            newlines. If there are no new (non-feedback) messages to return,
            `NO_NEW_MESSAGES_SENTINEL` is appended to the result so callers can
            distinguish the "no new messages" case.
        """
        messages = []

        messages.extend(self._unpulled_feedback)
        messages.extend(self._unpulled_messages)

        # If there were no messages, we add the sentinel
        if not self._unpulled_messages:
            logger.debug("No new messages to pull")
            messages.append(NO_NEW_MESSAGES_SENTINEL)

        self._unpulled_messages.clear()
        self._unpulled_feedback.clear()

        return "\n".join(messages)

    def handle_new_message(self, message: str) -> None:
        """Handle incoming messages."""
        self._unpulled_messages.append(message)
        logger.debug(
            "Received message",
            message=message,
            channel=self._get_my_channel(),
            queue_size=len(self._unpulled_messages),
        )

    def handle_feedback_message(self, message: str) -> None:
        """Handle feedback messages.

        These are handled differently from the regular messages because without that, we are not
        then also getting the NO_NEW_MESSAGES_SENTINEL which leads to big issues with the AI
        repeating itself.
        """
        self._unpulled_feedback.append(message)
        logger.debug(
            "Received feedback",
            message=message,
            channel=self._get_my_channel(),
            feedback_queue_size=len(self._unpulled_feedback),
        )

    def reset(self) -> None:
        """Reset the message handler state."""
        self._unpulled_messages.clear()
        self._unpulled_feedback.clear()
        self.session_id = None
        self.my_role = None
        self.other_role = None
        logger.debug("Message handler reset")

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

    @property
    def _is_running(self) -> bool:
        """Check if the subscriber is currently running."""
        if self._subscriber is not None:
            return self._subscriber.running
        return False
