from enum import Enum
from typing import Literal, override
from uuid import uuid4

from pydantic import UUID4, Field

from gptnt.common.servers import ClientMetadata
from gptnt.ktane.experiments.experiments import ExperimentSpec

type PlayerType = Literal["ai", "human"]
type PlayerRole = Literal["defuser", "expert"]


NO_NEW_MESSAGES_SENTINEL = "<no_new_messages>"


class UnhealthyPlayerError(Exception):
    """Raise when the player is unhealthy."""


class PlayerStage(Enum):
    """The stage of the experiment lifecycle that a Player is in."""

    boot = "boot"
    """Player is still starting."""

    waiting_for_experiment = "waiting_for_experiment"
    """The Player is ready to go."""

    ready_to_start_experiment = "ready_to_start_experiment"
    """The Player is ready to start the experiment."""

    in_experiment = "in_experiment"
    """The Player is currently playing a mission."""

    reflecting = "reflecting"
    """The Player is reflecting on the mission."""

    stopping = "stopping"
    """The Player is stopping the experiment and uploading to WandB."""


class PlayerMetadata(ClientMetadata):
    """Information about a player."""

    player_type: PlayerType

    player_role: PlayerRole | None = None
    player_name: str | None = None
    experiments_played: list[ExperimentSpec] = Field(default_factory=list)

    uuid: UUID4 = uuid4()

    stage: PlayerStage = PlayerStage.boot

    @override
    def __hash__(self) -> int:
        return hash(
            (
                self.player_type,
                self.player_role,
                self.player_name,
                *self.experiments_played,
                self.uuid,
            )
        )
