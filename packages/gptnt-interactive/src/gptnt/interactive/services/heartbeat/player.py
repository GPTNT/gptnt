import json
from typing import Annotated, override

from pydantic import BeforeValidator, PlainSerializer

from gptnt.core.specification import PlayerCapabilities
from gptnt.interactive.services.heartbeat.base import BaseHeartbeat, PlayerState


class PlayerHeartbeat(BaseHeartbeat, frozen=True):
    """Event for a player service to indicate that it is alive and well."""

    capabilities: Annotated[
        PlayerCapabilities,
        BeforeValidator(
            lambda capabilities: (
                json.loads(capabilities) if isinstance(capabilities, str) else capabilities
            )
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
