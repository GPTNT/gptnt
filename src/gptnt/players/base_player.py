import abc
from dataclasses import dataclass, field

import structlog

from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.players.metrics import PlayerEpisodeTracker
from gptnt.players.structures import PlayerMetadata

log = structlog.get_logger()


@dataclass(kw_only=True)
class BasePlayer(abc.ABC):
    """Base class for all players."""

    metadata: PlayerMetadata

    # Attributes that need to exist within the class
    dialogue_space_client: DialogueSpaceClient = field(init=False)

    tracker: PlayerEpisodeTracker

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

    async def on_experiment_stop(self) -> None:
        """Things to do when the experiment stops."""
        log.debug("Finishing wandb")
        self.tracker.on_game_end()

    async def disconnect_from_room(self) -> None:
        """Disconnect from the room."""
        if self.dialogue_space_client and self.dialogue_space_client.is_connected:
            await self.dialogue_space_client.disconnect()
            log.debug("Disconnected from room dialogue space.")

    @abc.abstractmethod
    async def run_parallel(self) -> None:
        """Run the player."""
        raise NotImplementedError

    @abc.abstractmethod
    async def run_sequential(self) -> None:
        """Run a single iteration of the decision making logic.

        For AI players only.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def health_check(self) -> None:
        """Check health of all relevant connections, logging exceptions if not healthy.

        Raises UnhealthyPlayerError if the player is unhealthy.
        """
        raise NotImplementedError
