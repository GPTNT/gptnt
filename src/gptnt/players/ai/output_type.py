from types import GenericAlias
from typing import Literal, TypeAliasType

from gptnt.ktane.actions import RelativeCoordinate
from gptnt.players.actions import SingleAlphabetLetter
from gptnt.players.ai.defuser import DefuserOutputT
from gptnt.players.ai.expert import ExpertOutputT


def get_defuser_output_type(variant: Literal["set_of_marks", "coordinates"]) -> GenericAlias:
    """Get the output type for the Defuser.

    This is mainly for Hydra and shouldn't be used anywhere else.
    """
    switcher = {
        "set_of_marks": DefuserOutputT[SingleAlphabetLetter],
        "coordinates": DefuserOutputT[RelativeCoordinate],
    }
    return switcher[variant]


def get_expert_output_type() -> TypeAliasType:
    """Get the output type for the Expert.

    This is mainly for Hydra and shouldn't be used anywhere else.
    """
    return ExpertOutputT
