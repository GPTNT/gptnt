from typing import Literal

from pydantic import BaseModel

from gptnt.core.ktane.state.bomb import BombState


class PlayerMessage[MessageT: str](BaseModel, frozen=True):
    """Model for a message sent to a player."""

    message: MessageT


class StopPlayerEvent(BaseModel, frozen=True):
    """Instruct a service to stop the currently running experiment."""

    event: Literal["stop-experiment"] = "stop-experiment"

    hard_crash: bool = False
    """If True, then it means that something has gone wrong with the experiment."""

    bomb_state: BombState | None = None
    """The final bomb state, if available.

    Used for feedback/reflection.
    """
