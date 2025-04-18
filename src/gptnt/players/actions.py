from enum import Enum

from pydantic import BaseModel, NonNegativeInt

from gptnt.ktane.actions import KtaneBaseAction, RelativeCoordinate


class ActionType(Enum):
    """Types of actions the agent can perform."""

    do_nothing = "do_nothing"
    send_message = "send_message"
    interact_game = "interact_game"


class BaseAction(BaseModel):
    """Base class for all actions."""

    thoughts: str | None = None


class DoNothingAction(BaseAction):
    """Create a 'do nothing' action."""

    action_type: ActionType = ActionType.do_nothing
    thoughts: str | None = None


class SendMessageAction(BaseAction):
    """Create a 'send message' action."""

    action_type: ActionType = ActionType.send_message
    message: str


type SetOfMarksLocation = NonNegativeInt
"""Set of marks location to interact with; must be an int >= 0."""

type InteractGameLocation = RelativeCoordinate | SetOfMarksLocation
"""Location-methods to interact with in the game."""


class InteractGameAction[LocationDataT: InteractGameLocation](
    BaseAction, KtaneBaseAction[LocationDataT]
):
    """Interaction action for the player to take in the game."""

    action_type: ActionType = ActionType.interact_game
