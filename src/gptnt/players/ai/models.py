from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from gptnt.ktane.actions import GameActionType
from gptnt.players.actions import InteractGameAction, SetOfMarksLocation

SoMAction = InteractGameAction[SetOfMarksLocation]


def dummy_set_of_marks_action_generator(
    messages: list[ModelMessage],
    info: AgentInfo,  # noqa: WPS110 ARG001
) -> ModelResponse:
    """Dummy function model that generates set of marks actions based on the number of messages."""
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
        SoMAction(action=GameActionType.click_release, location=1),
        SoMAction(action=GameActionType.zoom_out),
        # click again
        SoMAction(action=GameActionType.click_release, location=1),
        # Hold the button once
        SoMAction(action=GameActionType.hold, location=1),
        SoMAction(action=GameActionType.release),
        # Do it again
        SoMAction(action=GameActionType.hold, location=1),
        SoMAction(action=GameActionType.release),
        # Last time, and it should explode now (or not?)
        SoMAction(action=GameActionType.hold, location=1),
        SoMAction(action=GameActionType.release),
    ]

    # Return the action given the number of messages in the list
    action_to_perform = (
        actions_to_perform[len(messages)]
        if len(messages) < len(actions_to_perform)
        else SoMAction(action=GameActionType.click_release, location=1)
    )
    return ModelResponse(
        parts=[ToolCallPart("final_result", {"response": action_to_perform.as_model_return()})]
    )


class DummyDefuserModel(FunctionModel):
    """Dummy function model that generates set of marks actions based on the number of messages."""

    def __init__(self) -> None:
        super().__init__(dummy_set_of_marks_action_generator)
