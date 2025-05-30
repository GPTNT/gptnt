import asyncio
from dataclasses import dataclass
from functools import partial
from typing import Any
from uuid import uuid4

from aio_pika.abc import DateType
from aiormq.abc import DeliveredMessage
from faststream.rabbit import RabbitBroker, RabbitExchange
from faststream.rabbit.types import AioPikaSendableMessage
from pydantic import BaseModel
from structlog import get_logger

logger = get_logger()


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

        temp_queue = f"{prefix}.{uuid4()}"
        return_flag = asyncio.Event()

        async def callback(_message: Any) -> None:  # noqa: WPS430
            """Sets the flag on message delivery."""
            return_flag.set()

        _ = await channel.channel.queue_declare(temp_queue, auto_delete=True)
        _ = await channel.channel.basic_consume(queue=temp_queue, consumer_callback=callback)
        _ = await self.broker.publish(
            message=message, routing_key=self.routing_key, reply_to=temp_queue, timeout=fail_after
        )

        try:
            async with asyncio.timeout(fail_after):
                _ = await return_flag.wait()
        except TimeoutError:
            logger.exception("`TimeoutError` while waiting for response", message=message)
            _ = await channel.channel.queue_delete(queue=temp_queue)
            return False
        _ = await channel.channel.queue_delete(queue=temp_queue)
        return True

    async def publish_with_response[SendableResponse: BaseModel](
        self, message: SendableMessage, *, fail_after: float, response_type: type[SendableResponse]
    ) -> SendableResponse:
        """Publishes the message and awaits the response.

        Raises a TimeoutError after not receiving a response within `fail_after` seconds.
        Raises a Pydantic validation error if the received message is of an unexpected type.
        """
        if not (channel := self.broker._channel):  # noqa: SLF001
            # TODO: this should be a unique error type
            raise TimeoutError

        temp_queue = f"testing.{uuid4()}"
        return_flag = asyncio.Event()
        return_response: set[bytes] = set()

        async def callback(response: set[bytes], message: DeliveredMessage) -> None:  # noqa: WPS430
            """Sets the flag on message delivery."""
            response.add(message.body)
            return_flag.set()

        _ = await channel.channel.queue_declare(temp_queue, auto_delete=True)
        _ = await channel.channel.basic_consume(
            queue=temp_queue, consumer_callback=partial(callback, return_response)
        )
        _ = await self.broker.publish(
            message=message, routing_key=self.routing_key, reply_to=temp_queue, timeout=fail_after
        )

        async with asyncio.timeout(fail_after):
            _ = await return_flag.wait()
            _ = await channel.channel.queue_delete(queue=temp_queue)
            return response_type.model_validate_json(return_response.pop())
