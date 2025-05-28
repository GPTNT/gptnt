import asyncio
from dataclasses import dataclass, field

from pydantic.types import UUID4

from gptnt.api.events import ConnectEvent
from gptnt.api.experiment_manager.heartbeat_watchdog import HeartbeatWatchdog
from gptnt.players.spec import PlayerMetadata


@dataclass(kw_only=True)
class ConnectedService:
    """Collection of state for connected services."""

    connect_event: ConnectEvent
    watchdog: HeartbeatWatchdog
    is_ready: bool = field(default=False, init=False)
    in_experiment: bool = field(default=False, init=False)

    @property
    def uuid(self) -> UUID4:
        """UUID of the service."""
        return self.connect_event.uuid

    @property
    def watchdog_flag(self) -> asyncio.Event:
        """Flag used by the watchdog to determine if the service is still alive."""
        return self.watchdog.watchdog_flag


@dataclass(kw_only=True)
class ConnectedPlayerService(ConnectedService):
    """Collection of state for connected player services."""

    player_metadata: PlayerMetadata
