from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aio_pika import RobustExchange, RobustQueue
from faststream.rabbit import RabbitBroker, RabbitExchange, RabbitQueue
from faststream.rabbit.types import AioPikaSendableMessage

from gptnt.api.rabbit.api_route import APIRoute


@dataclass(kw_only=True)
class APIQueue[SendableMessage: AioPikaSendableMessage]:
    """Exposes functionality for controlling a RabbitMQ queue."""

    broker: RabbitBroker
    exchange: RabbitExchange
    queue_name: str

    def subscribe(
        self,
        callback: Callable[[SendableMessage], Any] | Callable[[SendableMessage], Awaitable[Any]],
    ) -> None:
        """Subscribes a callback to this queue.

        This should be called BEFORE starting the broker.
        """
        _ = self.broker.subscriber(self._queue, self.exchange)(callback)

    @property
    def route(self) -> APIRoute[SendableMessage]:
        """Getter for the route specific to this queue.

        This allows any defined queue to be published to individually.
        """
        return APIRoute(broker=self.broker, exchange=self.exchange, routing_key=self.queue_name)

    async def bind(self, routing_key: str) -> None:
        """Binds a new routing key to this queue."""
        pika_queue = await self._pika_queue()

        _ = await pika_queue.bind(exchange=await self._pika_exchange(), routing_key=routing_key)

        # All queues also bind to their own name
        _ = await pika_queue.bind(
            exchange=await self._pika_exchange(), routing_key=self.queue_name
        )

    async def unbind(self, routing_key: str | None = None) -> None:
        """Unbinds the routing key from the queue, or all bindings if none is provided."""
        pika_queue = await self._pika_queue()

        _ = await pika_queue.unbind(exchange=await self._pika_exchange(), routing_key=routing_key)

        # All queues also bind to their own name
        _ = await pika_queue.bind(
            exchange=await self._pika_exchange(), routing_key=self.queue_name
        )

    @property
    def _queue(self) -> RabbitQueue:
        """Private getter for the associated faststream.RabbitQueue."""
        return RabbitQueue(name=self.queue_name, routing_key=self.queue_name, auto_delete=True)

    async def _pika_exchange(self) -> RobustExchange:
        """Getter for the underlying pika.RobustExchange."""
        return await self.broker.declare_exchange(self.exchange)

    async def _pika_queue(self) -> RobustQueue:
        """Getter for the underlying pika.RobustExchange."""
        return await self.broker.declare_queue(self._queue)
