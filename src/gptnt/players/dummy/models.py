import json

import structlog
from pydantic_ai import TextPart
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel

from gptnt.ktane.actions import (
    GameActionType,
    GameActionTypeWithMagic,
    KtaneBaseAction,
    RelativeCoordinate,
)
from gptnt.players.actions import InteractGameAction, SendMessageAction, SetOfMarksLocation

logger = structlog.get_logger()

SoMAction = InteractGameAction[SetOfMarksLocation]


actions_to_perform = [
    SoMAction(action=GameActionType.rotate_left),
    SoMAction(action=GameActionType.rotate_right),
    SoMAction(action=GameActionType.flip),
    SoMAction(action=GameActionType.roll_down),
    SoMAction(action=GameActionType.roll_up),
    SoMAction(action=GameActionType.roll_up),
    SoMAction(action=GameActionType.roll_down),
    SoMAction(action=GameActionType.flip),
    # Now back at the front, click the first location
    SoMAction(action=GameActionType.click_release, location="A"),
    SoMAction(action=GameActionType.zoom_out),
    # click again
    SoMAction(action=GameActionType.click_release, location="A"),
    # Hold the button once
    SoMAction(action=GameActionType.hold, location="A"),
    SoMAction(action=GameActionType.release),
    # Do it again
    SoMAction(action=GameActionType.hold, location="A"),
    SoMAction(action=GameActionType.release),
    # Last time, and it should explode now (or not?)
    SoMAction(action=GameActionType.hold, location="A"),
    SoMAction(action=GameActionType.release),
]


class DummyDefuserModel(FunctionModel):
    """Dummy function model that generates set of marks actions based on the number of messages."""

    def __init__(self) -> None:
        super().__init__(self.dummy_action)

        self.actions_to_perform = iter(actions_to_perform)

    def dummy_action(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:  # noqa: WPS110 ARG002
        """Perform the dummy action."""
        if len(messages) < 2:  # noqa: PLR2004
            # Assume that it's a new game and reset it
            self.actions_to_perform = iter(actions_to_perform)

        try:
            action_to_perform = next(self.actions_to_perform)
        except StopIteration:
            # If we run out of actions, just return a click release action
            logger.debug("Ran out of actions to perform, returning click release action.")
            action_to_perform = SoMAction(action=GameActionType.click_release, location="A")

        model_response = action_to_perform.model_dump(
            mode="json", exclude_unset=True, exclude_defaults=True
        )
        model_response["action"] = action_to_perform.action.name
        return_as_dict = {"result": {"kind": "interact_game", "data": model_response}}

        return ModelResponse(parts=[TextPart(content=json.dumps(return_as_dict))])


class DummyExpertModel(FunctionModel):
    """Dummy function model that generates set of marks actions based on the number of messages."""

    def __init__(self) -> None:
        super().__init__(self.send_message)

    def send_message(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:  # noqa: WPS110 ARG002
        """Send a dummy message."""
        message = SendMessageAction(message=f"Message {len(messages)}")
        result_as_dict = {
            "result": {
                "kind": "send_message",
                "data": message.model_dump(exclude_unset=True, exclude_defaults=True, mode="json"),
            }
        }
        return ModelResponse(parts=[TextPart(content=json.dumps(result_as_dict))])


class MagicDefuserModel(FunctionModel):
    """Dummy function model that performs 'magic' actions."""

    def __init__(self) -> None:
        super().__init__(self.magic_function)

    def magic_function(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:  # noqa: WPS110 ARG002
        """Perform a magic action."""
        magic_action = KtaneBaseAction[GameActionTypeWithMagic, RelativeCoordinate](
            action="magic", location=None
        )

        model_response = magic_action.model_dump(
            mode="json", exclude_unset=True, exclude_defaults=True
        )
        model_response["action"] = magic_action.action

        return_as_dict = {"result": {"kind": "interact_game", "data": model_response}}
        return ModelResponse(parts=[TextPart(content=json.dumps(return_as_dict))])
