from dataclasses import dataclass
from functools import lru_cache

from gptnt.common.paths import Paths
from gptnt.ktane.state.bomb import BombState
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol
from gptnt.prompts.prompt_cache import PromptCache

paths = Paths()
"""Reflection messages for the player to receive when reflecting on the bomb state."""


@dataclass(kw_only=True)
class InvalidBombStateForReflectionError(ValueError):
    """Exception raised when the bomb state is invalid for reflection."""

    bomb_state: BombState


@lru_cache(maxsize=1)
def load_reflection_prompt(protocol: PlayerProtocol, capabilities: PlayerCapabilities) -> str:
    """Load the prompt for the given state."""
    reflection_prompt = PromptCache.get_text(
        paths.prompts.joinpath(
            "reflection_solo.txt" if protocol.is_playing_alone else "reflection.txt"
        )
    )
    if capabilities.thinking_method == "inner-monologue":
        return reflection_prompt.replace("thought", "think").replace(
            "reasoning", "thinking process"
        )
    return reflection_prompt


def convert_bomb_state_to_reflection(bomb_state: BombState) -> str:
    """Convert the bomb state to a reflection message.

    Raises:
        InvalidBombStateForReflectionError: If the bomb state is not valid for reflection.
    """
    final_message: str | None = None
    if bomb_state.is_detonated is True:
        if bomb_state.timer_module.seconds_remaining <= 0:
            # Bomb detonated because player ran out of time
            final_message = "The bomb exploded because time ran out."
        else:
            # Bomb detonated because player made too many mistakes
            final_message = "The bomb exploded because we made too many mistakes."

    if bomb_state.is_solved is True:
        # Player solved all modules on bomb
        final_message = "The bomb was defused successfully."

    if not final_message:
        raise InvalidBombStateForReflectionError(bomb_state=bomb_state)

    return final_message
