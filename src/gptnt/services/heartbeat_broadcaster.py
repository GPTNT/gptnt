from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from time import monotonic
from typing import TYPE_CHECKING, cast

import anyio
from coredis import Redis
from pydantic import UUID4
from structlog import get_logger
from whenever import TimeDelta

from gptnt.common.async_ops import periodic
from gptnt.services.events.heartbeat import Heartbeat, ReadyState
from gptnt.services.events.tombstone import FailureCategory, Tombstone
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

    _heartbeat_seq: int = field(default=0, init=False, repr=False)
    """Monotonically increasing counter of heartbeats sent."""

    _start_time: float = field(default_factory=monotonic, init=False, repr=False)
    """Monotonic timestamp of when the broadcaster was created."""

    @property
    def manifest(self) -> ServiceManifest[Heartbeat]:
        """Get the service manifest for this service."""
        return ServiceManifest(heartbeat=self.heartbeat_event())

    @property
    def heartbeat_key(self) -> str:
        """Get the Redis key for the heartbeat."""
        return f"heartbeat:{self.service_name}:{self.uuid}"

    @property
    def tombstone_key(self) -> str:
        """Get the Redis key for the shutdown tombstone."""
        return f"tombstone:{self.service_name}:{self.uuid}"

    @abstractmethod
    def heartbeat_event(self) -> Heartbeat:
        """Create the heartbeat event for this service that gets sent."""
        raise NotImplementedError

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
                # Write a tombstone so the watcher can distinguish graceful shutdown from crash
                await self._write_tombstone(reason=FailureCategory.graceful_shutdown)
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
        self._heartbeat_seq += 1
        heartbeat = self.heartbeat_event()

        _ = await self.redis.hset(
            self.heartbeat_key, cast("dict[StringT, ValueT]", heartbeat.model_dump(mode="json"))
        )
        _ = await self.redis.expire(
            self.heartbeat_key,
            TimeDelta(seconds=service_timeouts.heartbeat_expiration).py_timedelta(),
        )

    async def _write_tombstone(self, *, reason: FailureCategory) -> None:
        """Write a tombstone key to Redis on shutdown.

        Tombstones live longer than heartbeat keys so that the watcher can check them after the
        heartbeat key has already expired, allowing it to distinguish a graceful shutdown from an
        unexpected crash.
        """
        tombstone = Tombstone(
            uuid=self.uuid,
            service_name=self.service_name,
            final_ready_state=self.ready_state,
            reason=reason,
            heartbeats_sent=self._heartbeat_seq,
            uptime_seconds=round(monotonic() - self._start_time, 2),
        )
        _ = await self.redis.hset(
            self.tombstone_key, cast("dict[StringT, ValueT]", tombstone.model_dump(mode="json"))
        )
        _ = await self.redis.expire(
            self.tombstone_key,
            TimeDelta(seconds=service_timeouts.tombstone_expiration).py_timedelta(),
        )
        logger.debug(
            "Tombstone written",
            tombstone_key=self.tombstone_key,
            reason=reason.value,
            heartbeats_sent=self._heartbeat_seq,
        )
