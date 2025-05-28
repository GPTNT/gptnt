from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, NonNegativeInt
from pydantic.types import Tag

from gptnt.ktane.actions import KtaneBaseAction, RelativeCoordinate

type ActionType = Literal["do_nothing", "send_message", "interact_game"]
"""Type of action to take."""


class ThoughtsMixin(BaseModel):
    """Mixin for actions that can have thoughts."""

    thoughts: str | None = None
    """Thoughts of the player about the action."""


class DoNothingAction(BaseModel):
    """Create a 'do nothing' action."""

    command: Literal["do_nothing"] = "do_nothing"


class SendMessageAction(BaseModel):
    """Create a 'send message' action."""

    command: Literal["send_message"] = "send_message"
    message: str


def validate_single_alphabet_letter(letter: str) -> str:
    """Validate that the letter is a single alphabet letter."""
    if len(letter) != 1 or not letter.isalpha():
        raise ValueError("Must be a single alphabet letter (a-z).")
    return letter


type SingleAlphabetLetter = Annotated[
    str,
    BeforeValidator(lambda letter: letter.upper()),
    AfterValidator(validate_single_alphabet_letter),
]


type SetOfMarksLocation = NonNegativeInt | SingleAlphabetLetter
"""Set of marks location to interact with; must be an int >= 0, or a single letter a-z."""

type InteractGameLocation = RelativeCoordinate | SetOfMarksLocation
"""Location-methods to interact with in the game."""


class InteractGameAction[LocationDataT: InteractGameLocation](KtaneBaseAction[LocationDataT]):
    """Interaction action for the player to take in the game."""

    command: Literal["interact_game"] = "interact_game"


class DoNothingActionWithThoughts(DoNothingAction, ThoughtsMixin):
    """Create a 'do nothing' action with thoughts."""


class SendMessageActionWithThoughts(SendMessageAction, ThoughtsMixin):
    """Create a 'send message' action with thoughts."""


class InteractGameActionWithThoughts[LocationDataT: InteractGameLocation](
    InteractGameAction[LocationDataT], ThoughtsMixin
):
    """Interaction action for the player to take in the game with thoughts."""


ExpertOutputType = Annotated[
    Annotated[DoNothingAction, Tag("do_nothing")]
    | Annotated[SendMessageAction, Tag("send_message")],
    Tag("expert"),
]
ExpertOutputThoughtsType = Annotated[
    Annotated[DoNothingActionWithThoughts, Tag("do_nothing")]
    | Annotated[SendMessageActionWithThoughts, Tag("send_message")],
    Tag("expert"),
]

DefuserOutputType = Annotated[
    Annotated[DoNothingAction, Tag("do_nothing")]
    | Annotated[SendMessageAction, Tag("send_message")]
    | Annotated[InteractGameAction[SingleAlphabetLetter], Tag("interact_game")],
    Tag("defuser"),
]

DefuserOutputThoughtsType = Annotated[
    Annotated[DoNothingActionWithThoughts, Tag("do_nothing")]
    | Annotated[SendMessageActionWithThoughts, Tag("send_message")]
    | Annotated[InteractGameActionWithThoughts[SingleAlphabetLetter], Tag("interact_game")],
    Tag("defuser"),
]

SoloDefuserOutputType = Annotated[
    Annotated[DoNothingAction, Tag("do_nothing")]
    | Annotated[InteractGameAction[SingleAlphabetLetter], Tag("interact_game")],
    Tag("defuser"),
]
SoloDefuserOutputThoughtsType = Annotated[
    Annotated[DoNothingActionWithThoughts, Tag("do_nothing")]
    | Annotated[InteractGameActionWithThoughts[SingleAlphabetLetter], Tag("interact_game")],
    Tag("defuser"),
]

PlayerOutputType = (
    ExpertOutputType
    | DefuserOutputType
    | SoloDefuserOutputType
    | ExpertOutputThoughtsType
    | DefuserOutputThoughtsType
    | SoloDefuserOutputThoughtsType
)


type InteractGameActionType = (
    KtaneBaseAction[RelativeCoordinate]
    | KtaneBaseAction[InteractGameLocation]
    | InteractGameAction[InteractGameLocation]
    | InteractGameActionWithThoughts[InteractGameLocation]
)
