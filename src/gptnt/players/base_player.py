import abc
from dataclasses import dataclass, field
from typing import Literal

import structlog
from pydantic import Field

from gptnt.common.servers import ClientMetadata
from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.ktane.experiments.experiments import ExperimentSpec

log = structlog.get_logger()

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


@dataclass(kw_only=True)
class BasePlayer(abc.ABC):
    """Base class for all players."""

    metadata: PlayerMetadata

    # Attributes that need to exist within the class
    dialogue_space_client: DialogueSpaceClient = field(init=False)

    @abc.abstractmethod
    async def on_startup(self) -> None:
        """Run on startup.

        Basically, to run BEFORE the player connects to the Experiment Manager.
        """
        raise NotImplementedError

    # @abc.abstractmethod
    # async def on_shutdown(self) -> None:
    #     """Run on shutdown.

    #     Basically, to run AFTER the player disconnects from the Experiment Manager.
    #     """
    #     raise NotImplementedError

    @abc.abstractmethod
    async def connect(self) -> None:
        """Connect to all the clients."""
        raise NotImplementedError

    async def disconnect_from_room(self) -> None:
        """Disconnect from the room."""
        if self.dialogue_space_client and self.dialogue_space_client.is_connected:
            await self.dialogue_space_client.disconnect()
            log.debug("Disconnected from room dialogue space.")

    @abc.abstractmethod
    async def run(self) -> None:
        """Run the player."""
        raise NotImplementedError

    async def run_once(self) -> None:
        """Run a single iteration of the decision making logic.

        AI players only.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def health_check(self) -> None:
        """Check health of all relevant connections, logging exceptions if not healthy.

        Raises UnhealthyPlayerError if the player is unhealthy.
        """
        raise NotImplementedError
