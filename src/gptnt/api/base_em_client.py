from abc import ABC, abstractmethod
from contextlib import suppress
from dataclasses import dataclass
from functools import cached_property
from types import TracebackType
from typing import override

import logfire
from pydantic.types import UUID4
from structlog import get_logger

from gptnt.api.base_rabbitmq_client import BaseRabbitMQClient
from gptnt.api.events import ConnectEvent, HeartbeatEvent, ReadyEvent
from gptnt.common.async_ops import busy_wait_interval, until


class EMConnectionFailedError(Exception):
    """Error representing failure to connect with the EM."""


class EMConnectionClosedError(Exception):
    """Error represeting the EM connection being closed."""


logger = get_logger()


@dataclass(kw_only=True)
class BaseEMClient(BaseRabbitMQClient, ABC):
    """Base class for services connecting to the EM.

    Implements EM connection and heartbeats automatically based on generic connection type.
    """

    uuid: UUID4

    @cached_property
    @abstractmethod
    def connection_message(self) -> ConnectEvent:
        """Return the connection message sent to the EM on start."""
        raise NotImplementedError(
            "Please override `connection_message` to specify the message to send to the EM on start"
        )

    @logfire.instrument("Ready -> EM")
    async def ready(self) -> None:
        """Send a ReadyEvent to the EM to make the service eligible for matchmaking."""
        await until(get_value=lambda: self.broker.running, target=True)
        await busy_wait_interval()
        await self.api_queues.experiment_ready().route.publish(ReadyEvent(uuid=self.uuid))

    @override
    async def lifespan_setup(self) -> None:
        """EM clients require extra startup logic on top of base handler logic."""
        _ = self.background_tasks.create_task(self._connect())

    async def _connect(self) -> None:
        """Blocks until a succesful connection to the EM is established."""
        with logfire.span("Connect to EM"):
            # Wait until the broker connects to RabbitMQ
            await until(get_value=lambda: self.broker.running, target=True)

            is_connected = await self.api_queues.experiment_connections().route.publish_with_ack(
                message=self.connection_message, fail_after=1.0
            )
            logger.info("Connected to Experiment Manager")

        if is_connected:
            _ = self.background_tasks.create_task(self._heartbeat())
        else:
            logger.error("Failed to connect to Experiment Manager")
            raise EMConnectionFailedError

    async def _heartbeat(self) -> None:
        """Continuously performs heartbeats with the EM."""
        with suppress(TimeoutError):
            await until(
                get_value=lambda: self.api_queues.experiment_heartbeat().route.publish_with_ack(
                    message=HeartbeatEvent(uuid=self.uuid), fail_after=1.0, prefix="heartbeat"
                ),
                target=False,
            )
        logger.error("Experiment Manager failed heartbeat, assumed dead")
        raise EMConnectionClosedError

    @override
    async def _background_task_exception_handler_wrapper(
        self,
        exc_type: type[BaseException] | None = None,
        exc_obj: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        """EM clients require checking for disconnections on top of base handler logic."""
        # TODO: May be good to replace these with a graceful restart in production
        if exc_type is EMConnectionFailedError:
            await self.shutdown(
                exit_message="Failed to connect to Experiment Manager, shutting down app."
            )
        elif exc_type is EMConnectionClosedError:
            await self.shutdown(
                exit_message="Experiment Manager failed to respond to heartbeat, shutting down app."
            )
        else:
            await super()._background_task_exception_handler_wrapper(exc_type, exc_obj, exc_tb)
