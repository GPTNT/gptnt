from typing import Any, Literal, Union

from gptnt.ktane.actions import RelativeCoordinate
from gptnt.players.actions import SingleAlphabetLetter
from gptnt.players.ai.defuser import DefuserOutputT
from gptnt.players.ai.expert import ExpertOutputT


def get_defuser_output_type(
    variant: Literal["set_of_marks", "coordinates", "gemini", "string"],
) -> Any:
    """Get the output type for the Defuser.

    This is mainly for Hydra and shouldn't be used anywhere else.
    """
    switcher = {
        "set_of_marks": DefuserOutputT[SingleAlphabetLetter],
        "coordinates": DefuserOutputT[RelativeCoordinate],
        # Gemini doesn't support recursive structured outputs, so we need to parse the output
        # separately
        "gemini": Union[ExpertOutputT, str],  # noqa: UP007
        "string": str,
    }
    return switcher[variant]


def get_expert_output_type(variant: Literal["structured", "string"]) -> Any:
    """Get the output type for the Expert.

    This is mainly for Hydra and shouldn't be used anywhere else.
    """
    if variant == "structured":
        return str
    return ExpertOutputT
