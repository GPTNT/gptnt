from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import anyio
from coredis import Redis
from pydantic import UUID4
from structlog import get_logger
from whenever import TimeDelta

from gptnt.common.async_ops import periodic
from gptnt.services.events.heartbeat import Heartbeat, ReadyState
from gptnt.services.registry.manifest import ServiceManifest
from gptnt.services.timeouts import ServiceTimeouts

if TYPE_CHECKING:
    from coredis.typing import StringT, ValueT

service_timeouts = ServiceTimeouts()
logger = get_logger()


@dataclass(kw_only=True)
class HeartbeatBroadcaster(ABC):
    """Base class that includes the logic for sending the heartbeats.

    This will get used by the game/player services to send periodic heartbeats to Redis so it can
    be tracked by the registry.
    """

    redis: Redis[str]
    service_name: str
    uuid: UUID4
    ready_state: ReadyState = field(default=ReadyState.not_ready)

    @abstractmethod
    def heartbeat_event(self) -> Heartbeat:
        """Create the heartbeat event for this service that gets sent."""
        raise NotImplementedError

    @property
    def manifest(self) -> ServiceManifest[Heartbeat]:
        """Get the service manifest for this service."""
        return ServiceManifest(heartbeat=self.heartbeat_event())

    @property
    def heartbeat_key(self) -> str:
        """Get the Redis key for the heartbeat."""
        return f"heartbeat:{self.service_name}:{self.uuid}"

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
        """Lifespan for the Heartbeat Manager."""
        async with self.redis, anyio.create_task_group() as tg:
            tg.start_soon(self.heartbeat_loop)
            self.ready_state = ReadyState.ready
            try:  # noqa: WPS243
                yield
            finally:
                # Ensure the heartbeat loop is cancelled on shutdown
                tg.cancel_scope.cancel()
                # Send a final heartbeat to tell the EM we are shutting down
                self.ready_state = ReadyState.not_ready
                await self.send_heartbeat()
                logger.debug("Heartbeat loop cancelled")

    async def heartbeat_loop(self) -> None:
        """Send periodic heartbeats.

        Each heartbeat is set to expire after the configured heartbeat expiration time.
        """
        logger.debug("Starting heartbeat loop")
        async for _ in periodic(service_timeouts.heartbeat_repeat_interval):
            await self.send_heartbeat()

    async def send_heartbeat(self) -> None:
        """Send a heartbeat to the Redis."""
        _ = await self.redis.hset(
            self.heartbeat_key,
            cast("dict[StringT, ValueT]", self.heartbeat_event().model_dump(mode="json")),
        )
        _ = await self.redis.expire(
            self.heartbeat_key,
            TimeDelta(seconds=service_timeouts.heartbeat_expiration).py_timedelta(),
        )
