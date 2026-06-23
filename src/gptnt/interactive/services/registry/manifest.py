from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, override

from pydantic.types import UUID4
from structlog import get_logger
from whenever import Instant

from gptnt.interactive.services.heartbeat.base import ReadyState
from gptnt.interactive.services.heartbeat.game import GameHeartbeat
from gptnt.interactive.services.heartbeat.player import PlayerHeartbeat
from gptnt.interactive.services.timeouts import ServiceTimeouts

logger = get_logger()
service_timeouts = ServiceTimeouts()


class ServiceState(Enum):
    """State of a connected service."""

    idle = "idle"
    in_experiment = "in_experiment"
    cleanup = "cleanup"
    not_ready = "not_ready"


@dataclass(kw_only=True)
class ServiceManifest[HeartbeatT: GameHeartbeat | PlayerHeartbeat]:
    """Manifest for a service that's running in the registry."""

    heartbeat: HeartbeatT
    state: ServiceState = field(default=ServiceState.idle, init=False)
    """The service state is the EM's understanding of the state at a 'higher' level."""

    @override
    def __str__(self) -> str:
        return f"ServiceManifest(type={self.service_type}, uuid={self.uuid}, state={self.state})"

    @property
    def uuid(self) -> UUID4:
        """UUID of the service."""
        return self.heartbeat.uuid

    @property
    def service_type(self) -> Literal["player", "game"]:
        """Get the service type as a name."""
        match self.heartbeat:
            case PlayerHeartbeat():
                return "player"
            case GameHeartbeat():
                return "game"

    @property
    def is_ready(self) -> bool:
        """Check if the service is ready."""
        return self.heartbeat.ready_state == ReadyState.ready

    @property
    def is_not_ready(self) -> bool:
        """Check if the service is not ready."""
        return self.heartbeat.ready_state == ReadyState.not_ready

    @property
    def is_expired(self) -> bool:
        """Check if the service is expired."""
        return (
            self.heartbeat.timestamp.add(seconds=service_timeouts.heartbeat_expiration)
            <= Instant.now()
        )

    @property
    def heartbeat_key(self) -> str:
        """Get the Redis key for the heartbeat."""
        return f"heartbeat:{self.heartbeat.service_name}:{self.heartbeat.uuid}"

    @property
    def tombstone_key(self) -> str:
        """Get the Redis key for the shutdown tombstone."""
        return f"tombstone:{self.heartbeat.service_name}:{self.heartbeat.uuid}"


type PlayerServiceManifest = ServiceManifest[PlayerHeartbeat]
type GameServiceManifest = ServiceManifest[GameHeartbeat]
