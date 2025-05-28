import asyncio
from dataclasses import dataclass, field
from typing import Any

from pydantic.types import UUID4


@dataclass(kw_only=True)
class HeartbeatWatchdogTriggeredError(Exception):
    """Error representing a failed heartbeat watchdog."""

    uuid: UUID4
    metadata: dict[str, Any]


@dataclass(kw_only=True)
class HeartbeatWatchdog:
    """Watchdog for tracking periodic heartbeats.

    `watchdog_flag.set()` must be called every `fail_after` seconds otherwise the passed
    exception will be raised in the calling context. Must be started using `watchdog_loop`,
    ideally in some task group.
    """

    fail_after: float
    fail_exception: BaseException

    watchdog_flag: asyncio.Event = field(default_factory=asyncio.Event, init=False)

    async def watchdog_loop(self) -> None:
        """Runs until `watchdog_flag` is not set in time, then raises `fail_exception`."""
        while True:
            try:
                async with asyncio.timeout(self.fail_after):
                    self.watchdog_flag.clear()
                    _ = await self.watchdog_flag.wait()

            except TimeoutError:
                raise self.fail_exception  # noqa: B904
