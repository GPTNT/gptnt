from pydantic import BaseModel


class DoNothingAction(BaseModel):
    """Create a 'do nothing' action for a player to take."""

    action_type: str = "do_nothing"


class SendMessageAction(BaseModel):
    """Create a 'send message' action for a player to take."""

    action_type: str = "send_message"
    message: str
