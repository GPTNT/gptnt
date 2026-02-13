import json
import os
import socket
from enum import Enum
from typing import Annotated, Literal, override

from pydantic import BeforeValidator, Field, PlainSerializer, Tag
from whenever import Instant

from gptnt.ktane.state.game import GameState
from gptnt.players.specification import PlayerCapabilities
from gptnt.services.events.base import BaseEvent
from gptnt.services.events.player import PlayerState


class ReadyState(Enum):
    """Enum to represent the readiness state of a service."""

    ready = "ready"
    not_ready = "not_ready"


class BaseHeartbeat(BaseEvent, frozen=True):
    """Event for a service to indicate that it is alive and well.

    This is also used as connect events.
    """

    event: Literal["heartbeat"] = "heartbeat"
    timestamp: Instant = Field(default_factory=Instant.now)
    ready_state: ReadyState

    # Diagnostic fields for richer error context
    heartbeat_seq: int = 0
    """Monotonically increasing sequence number.

    Allows watchers to detect gaps.
    """

    uptime_seconds: float = Field(default=0)
    """How long this service has been alive (seconds since broadcaster started)."""

    pid: int = Field(default_factory=os.getpid)
    """Process ID of the service, for correlating with logs and container diagnostics."""

    hostname: str = Field(default_factory=socket.gethostname)
    """Hostname of the machine running the service."""

    @property
    def is_idle(self) -> bool:
        """Check if the service is in an idle state."""
        return self.ready_state == ReadyState.ready


class GameHeartbeat(BaseHeartbeat, frozen=True):
    """Event for a game service to indicate that it is alive and well."""

    state: GameState
    ktane_url: str
    """Current URL for the game itself."""

    @property
    @override
    def is_idle(self) -> bool:
        """Check if the game is in an idle state."""
        return self.state == GameState.main_menu and super().is_idle


class PlayerHeartbeat(BaseHeartbeat, frozen=True):
    """Event for a player service to indicate that it is alive and well."""

    capabilities: Annotated[
        PlayerCapabilities,
        BeforeValidator(
            lambda capabilities: json.loads(capabilities)
            if isinstance(capabilities, str)
            else capabilities
        ),
        PlainSerializer(
            lambda capabilities: capabilities.model_dump_json(), return_type=str, when_used="json"
        ),
    ]
    state: PlayerState

    @property
    @override
    def is_idle(self) -> bool:
        """Check if the player is in an idle state."""
        return self.state == PlayerState.idle and super().is_idle


Heartbeat = Annotated[GameHeartbeat, Tag("player")] | Annotated[PlayerHeartbeat, Tag("game")]
