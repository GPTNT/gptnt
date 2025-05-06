from enum import Enum

from pydantic import BaseModel
from pydantic.types import UUID4

from gptnt.common.servers import ClientMetadata
from gptnt.ktane.experiments.experiments import ExperimentSpec
from gptnt.players.structures import PlayerMetadata


class RoomStage(Enum):
    """The stage of the experiment lifecycle that a RoomManager is in."""

    boot = "boot"
    """RoomManager is still starting."""

    ready_for_config = "ready_for_config"
    """The RoomManager is ready to receive a mission config and players."""

    ready_for_start = "ready_for_start"
    """The RoomManager is ready to start the mission (players connected)."""

    in_experiment = "in_experiment"
    """The RoomManager is currently playing a mission."""

    done = "done"
    """The RoomManager is finished playing a mission."""


class RoomMetadata(ClientMetadata):
    """Information about a Room that needed to maintain a connection."""

    dialogue_space_url: str
    ktane_url: str
    state: RoomStage
    uuid: UUID4


class GameMetadata(BaseModel):
    """Information about a given experiment."""

    experiment_spec: ExperimentSpec
    """The spec of the experiment."""

    player_metadata: PlayerMetadata
    """The metadata of the player that played the experiment."""

    game_id: UUID4
    """The ID of the game."""

    @property
    def requires_multiple_images_per_observation(self) -> bool:
        """Whether the experiment requires multiple images per observation."""
        return self.experiment_spec.mission_spec.requires_multiple_images_per_observation
