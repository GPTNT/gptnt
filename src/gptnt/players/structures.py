from typing import Literal, override
from uuid import uuid4

from pydantic import UUID4, Field

from gptnt.common.servers import ClientMetadata
from gptnt.ktane.experiments.experiments import ExperimentSpec

type PlayerType = Literal["ai", "human"]
type PlayerRole = Literal["defuser", "expert"]


class UnhealthyPlayerError(Exception):
    """Raise when the player is unhealthy."""


class PlayerMetadata(ClientMetadata):
    """Information about a player."""

    player_type: PlayerType

    player_role: PlayerRole | None = None
    player_name: str | None = None
    experiments_played: list[ExperimentSpec] = Field(default_factory=list)

    uuid: UUID4 = uuid4()

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
