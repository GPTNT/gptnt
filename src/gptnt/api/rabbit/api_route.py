import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from aio_pika import RobustChannel
from aio_pika.abc import DateType
from aiormq.abc import ConsumerCallback, DeliveredMessage
from faststream.rabbit import RabbitBroker, RabbitExchange
from faststream.rabbit.types import AioPikaSendableMessage
from pydantic import BaseModel
from structlog import get_logger

logger = get_logger()


@asynccontextmanager
async def temporary_queue(
    channel: RobustChannel, consumer_callback: ConsumerCallback, prefix: str = "testing"
) -> AsyncGenerator[str, None]:
    """Creates a temporary queue for consuming messages."""
    temp_queue = f"{prefix}.{uuid4()}"
    _ = await channel.channel.queue_declare(temp_queue, auto_delete=True)
    consume_ok = await channel.channel.basic_consume(
        queue=temp_queue, consumer_callback=consumer_callback
    )
    assert consume_ok.consumer_tag, "Consumer tag should not be None"
    yield temp_queue
    _ = await channel.channel.basic_cancel(consume_ok.consumer_tag)
    _ = await channel.channel.queue_delete(queue=temp_queue)


@dataclass(kw_only=True)
class APIRoute[SendableMessage: AioPikaSendableMessage]:
    """Exposes functionality for publishing to a specific routing key.

    This can target one or many queues.
    """

    broker: RabbitBroker
    exchange: RabbitExchange
    routing_key: str

    async def publish(
        self, message: SendableMessage, *, expiration: DateType | None = None
    ) -> None:
        """Publishes a message to the route."""
        _ = await self.broker.publish(
            message=message,
            exchange=self.exchange,
            routing_key=self.routing_key,
            expiration=expiration,
        )

    async def publish_with_ack(
        self, message: SendableMessage, *, fail_after: float, prefix: str = "testing"
    ) -> bool:  # noqa: WPS217
        """Publishes a message to the route and awaits a response.

        Returns True if a response is received within `fail_after` seconds, else False.
        """
        if not (channel := self.broker._channel):  # noqa: SLF001
            return False

        return_flag = asyncio.Event()

        async def callback(_message: Any) -> None:  # noqa: WPS430
            """Sets the flag on message delivery."""
            return_flag.set()

        async with temporary_queue(
            channel=channel, consumer_callback=callback, prefix=f"{prefix}.{uuid4()}"
        ) as temp_queue:
            _ = await channel.channel.queue_declare(temp_queue, auto_delete=True)
            consume_ok = await channel.channel.basic_consume(
                queue=temp_queue, consumer_callback=callback
            )
            assert consume_ok.consumer_tag, "Consumer tag should not be None"
            _ = await self.broker.publish(
                message=message,
                routing_key=self.routing_key,
                reply_to=temp_queue,
                timeout=fail_after,
            )

            try:
                async with asyncio.timeout(fail_after):
                    _ = await return_flag.wait()
            except TimeoutError:
                logger.exception("`TimeoutError` while waiting for response", message=message)
                return False
            return True

    async def publish_with_response[SendableResponse: BaseModel](
        self, message: SendableMessage, *, fail_after: float, response_type: type[SendableResponse]
    ) -> SendableResponse:
        """Publishes the message and awaits the response.

        Raises a TimeoutError after not receiving a response within `fail_after` seconds.
        Raises a Pydantic validation error if the received message is of an unexpected type.
        """
        if not (channel := self.broker._channel):  # noqa: SLF001
            logger.error("No channel available for publishing", message=message)
            # TODO: this should be a unique error type
            raise TimeoutError

        return_flag = asyncio.Event()
        response_data: list[bytes] = []

        async def callback(message: DeliveredMessage) -> None:  # noqa: WPS430
            """Sets the flag on message delivery."""
            response_data.append(message.body)
            return_flag.set()

        async with temporary_queue(
            channel=channel, consumer_callback=callback, prefix="testing"
        ) as temp_queue:
            _ = await self.broker.publish(
                message=message,
                routing_key=self.routing_key,
                reply_to=temp_queue,
                timeout=fail_after,
            )

            logger.debug("Waiting for response")
            try:
                async with asyncio.timeout(fail_after):
                    _ = await return_flag.wait()
            except TimeoutError:
                logger.exception("`TimeoutError` while waiting for response", message=message)
                raise
            try:
                return response_type.model_validate_json(response_data[0])
            except Exception:
                logger.exception("Failed to validate response data", message=message)
                raise
