import abc
from typing import ClassVar, Literal

from gptnt.dialogue_space.client import DialogueSpaceClient


class UnhealthyPlayerError(Exception):
    """Raise when the player is unhealthy."""


class BasePlayer(abc.ABC):
    """Base class for all players."""

    role: ClassVar[Literal["expert", "defuser"]]

    # Attributes that need to exist within the class
    dialogue_space_client: DialogueSpaceClient

    @abc.abstractmethod
    async def connect(self) -> None:
        """Connect to all the clients."""
        raise NotImplementedError

    @abc.abstractmethod
    async def run(self) -> None:
        """Run the player."""
        raise NotImplementedError

    @abc.abstractmethod
    async def health_check(self) -> None:
        """Check health of all relevant connections, logging exceptions if not healthy.

        Raises UnhealthyPlayerError if the player is unhealthy.
        """
        raise NotImplementedError
