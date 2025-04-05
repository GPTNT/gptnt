from enum import Enum
from typing import Literal

from pydantic import BaseModel, NonNegativeInt

from gptnt.ktane.actions import KtaneBaseAction, RelativeCoordinate


class ActionType(Enum):
    """Types of actions the agent can perform."""

    do_nothing = "do_nothing"
    send_message = "send_message"
    interact_game = "interact_game"


class DoNothingAction(BaseModel):
    """Create a 'do nothing' action."""

    action_type: Literal[ActionType.do_nothing] = ActionType.do_nothing


class SendMessageAction(BaseModel):
    """Create a 'send message' action."""

    action_type: Literal[ActionType.send_message] = ActionType.send_message
    message: str


type SetOfMarksLocation = NonNegativeInt
"""Set of marks location to interact with; must be an int >= 0."""

type InteractGameLocation = RelativeCoordinate | SetOfMarksLocation
"""Location-methods to interact with in the game."""


class InteractGameAction[LocationDataT: InteractGameLocation](KtaneBaseAction[LocationDataT]):
    """Interaction action for the player to take in the game."""

    action_type: Literal[ActionType.interact_game] = ActionType.interact_game
