from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from gptnt.common.paths import Paths
from gptnt.ktane.state.bomb import BombState
from gptnt.prompts.prompt_cache import PromptCache

paths = Paths()


type ReflectionMessage = Literal["terminated-exploded", "truncated-exploded", "terminated-defused"]
"""Reflection messages for the player to receive when reflecting on the bomb state."""


@dataclass(kw_only=True)
class InvalidBombStateForReflectionError(ValueError):
    """Exception raised when the bomb state is invalid for reflection."""

    bomb_state: BombState


@lru_cache(maxsize=1)
def load_reflection_prompt() -> str:
    """Load the prompt for the given state."""
    return PromptCache.get_text(paths.prompts.joinpath("reflection.txt"))


def convert_bomb_state_to_reflection(bomb_state: BombState) -> ReflectionMessage:
    """Convert the bomb state to a reflection message.

    Raises:
        InvalidBombStateForReflectionError: If the bomb state is not valid for reflection.
    """
    final_message: ReflectionMessage | None = None
    if bomb_state.is_detonated is True:
        if bomb_state.timer_module.seconds_remaining <= 0:
            # Bomb detonated because player ran out of time
            final_message = "terminated-exploded"
        else:
            # Bomb detonated because player made too many mistakes
            final_message = "truncated-exploded"

    if bomb_state.is_solved is True:
        # Player solved all modules on bomb
        final_message = "terminated-defused"

    if not final_message:
        raise InvalidBombStateForReflectionError(bomb_state=bomb_state)

    return final_message
