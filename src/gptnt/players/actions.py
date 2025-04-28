from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, NonNegativeInt

from gptnt.ktane.actions import KtaneBaseAction, RelativeCoordinate

type ActionType = Literal["do_nothing", "send_message", "interact_game"]


class BaseAction(BaseModel):
    """Base class for all actions."""

    thoughts: str | None = None


class DoNothingAction(BaseAction):
    """Create a 'do nothing' action."""

    action_type: Literal["do_nothing"] = "do_nothing"


class SendMessageAction(BaseAction):
    """Create a 'send message' action."""

    action_type: Literal["send_message"] = "send_message"
    message: str


type SingleAlphabetLetter = Annotated[
    str,
    BeforeValidator(lambda letter: letter.lower()),
    AfterValidator(lambda letter: len(letter) == 1),
    AfterValidator(lambda letter: letter.isalpha()),
]

type SetOfMarksLocation = NonNegativeInt | SingleAlphabetLetter
"""Set of marks location to interact with; must be an int >= 0, or a single letter a-z."""

type InteractGameLocation = RelativeCoordinate | SetOfMarksLocation
"""Location-methods to interact with in the game."""


class InteractGameAction[LocationDataT: InteractGameLocation](
    BaseAction, KtaneBaseAction[LocationDataT]
):
    """Interaction action for the player to take in the game."""

    action_type: Literal["interact_game"] = "interact_game"
