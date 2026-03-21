from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field
from pydantic.types import UUID4
from whenever import Instant

from gptnt.services.heartbeat.base import BaseEvent, ReadyState


class FailureCategory(Enum):
    """Categories of heartbeat read failures for diagnostics."""

    never_connected = "never_connected"
    graceful_shutdown = "graceful_shutdown"
    unexpected_disappearance = "unexpected_disappearance"
    partial_hash = "partial_hash"


class Tombstone(BaseEvent, frozen=True):
    """Tombstone written on shutdown to indicate a service has stopped."""

    event: Literal["tombstone"] = "tombstone"
    timestamp: Instant = Field(default_factory=Instant.now)
    final_ready_state: ReadyState

    reason: FailureCategory
    heartbeats_sent: int
    uptime_seconds: float


class ServiceExpiredContext(BaseModel):
    """Diagnostic context gathered by the registry when a service expires.

    This bundles all the Redis-probed information (tombstone, key state) into a single
    object that gets passed to the EM's `_handle_expired_service` for rich logging.
    """

    service_uuid: UUID4
    service_type: str

    # Tombstone info (None if no tombstone was found — i.e. unexpected death)
    tombstone: Annotated[
        Tombstone | None, BeforeValidator(lambda tomb: tomb if tomb else None)
    ] = None

    # Heartbeat key state at the moment of expiry
    heartbeat_key_exists: bool = False
    heartbeat_key_ttl: int = -2
    remaining_heartbeat_fields: dict[str, Any] = Field(default_factory=dict)

    # Last heartbeat we had in the registry (from the manifest)
    last_heartbeat_seq: int | None = None
    last_uptime_seconds: float | None = None
    last_pid: int | None = None
    last_hostname: str | None = None

    @property
    def failure_category(self) -> FailureCategory:
        """Determine the failure category from the gathered diagnostics."""
        if self.tombstone:
            return self.tombstone.reason
        if self.heartbeat_key_exists and self.remaining_heartbeat_fields:
            return FailureCategory.partial_hash
        return FailureCategory.unexpected_disappearance
