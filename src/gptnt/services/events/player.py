from enum import IntEnum
from typing import Literal

from pydantic import BaseModel

from gptnt.ktane.state.bomb import BombState


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
