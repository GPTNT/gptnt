import os
import socket
from enum import Enum, IntEnum
from typing import Literal

from pydantic import UUID4, BaseModel, Field
from whenever import Instant


class BaseEvent(BaseModel, frozen=True):
    """Base class for events sent from services to the EM, stored in Redis."""

    uuid: UUID4
    """UUID of the service sending the event."""

    service_name: str
    """Service name."""


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


class PlayerState(IntEnum):
    """States for the player service."""

    idle = 0
    """Player is waiting to be configured for an experiment."""

    configuring_experiment = 1
    """The player is being configured for an experiment."""

    # >2 mean they are in an experiment
    waiting_for_turn = 2
    """Player is configured and waiting for their turn."""

    # >3 means they are performing actions in the experiment
    performing_forward_pass = 3
    """Player is performing a forward pass in the experiment."""

    # Below are more fine-grained states so we can track the progress
    pulling_messages = 4
    """Player is pulling messages."""
    waiting_for_observation = 5
    """Player is waiting for an observation from the game client."""
    preparing_agent_input = 6
    """Player is preparing input for the AI."""
    waiting_for_action = 7
    """Player is waiting for the output from the AI."""
    performing_action = 8
    """Player is performing an action based on the AI's output."""

    # >9 are the ending states
    stopping = 9
    """Player told to stop."""
    reflecting = 10
    """Performing reflection."""
    uploading = 11
    """Uploading results."""
    cleanup = 12
    """Cleaning up after experiment."""
