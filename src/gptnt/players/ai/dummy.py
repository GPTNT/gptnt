import structlog
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from gptnt.ktane.actions import GameActionType
from gptnt.players.actions import InteractGameAction, SendMessageAction, SetOfMarksLocation

logger = structlog.get_logger()

SoMAction = InteractGameAction[SetOfMarksLocation]


actions_to_perform = iter(
    [
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
)


def dummy_set_of_marks_action_generator(
    messages: list[ModelMessage],  # noqa:  ARG001
    info: AgentInfo,  # noqa: WPS110 ARG001
) -> ModelResponse:
    """Dummy function model that generates set of marks actions based on the number of messages."""
    try:
        action_to_perform = next(actions_to_perform)
    except StopIteration:
        # If we run out of actions, just return a click release action
        logger.warning("Ran out of actions to perform, returning click release action.")
        action_to_perform = SoMAction(action=GameActionType.click_release, location="A")

    model_response = action_to_perform.model_dump(mode="json", exclude=["thoughts", "action_type"])  # pyright: ignore[reportArgumentType]
    model_response["action"] = action_to_perform.action.name

    logger.info("Sending action", action=model_response)

    return ModelResponse(parts=[ToolCallPart("final_result", {"response": model_response})])


def dummy_message_generator(
    messages: list[ModelMessage],
    info: AgentInfo,  # noqa: WPS110 ARG001
) -> ModelResponse:
    """Dummy function model that generates set of marks actions based on the number of messages."""
    message = SendMessageAction(message=f"Message {len(messages)}")
    return ModelResponse(
        parts=[
            ToolCallPart(
                "final_result_SendMessageAction",
                message.model_dump(exclude=["thoughts", "action_type"], mode="json"),  # pyright: ignore[reportArgumentType]
            )
        ]
    )


class DummyDefuserModel(FunctionModel):
    """Dummy function model that generates set of marks actions based on the number of messages."""

    def __init__(self) -> None:
        super().__init__(dummy_set_of_marks_action_generator)


class DummyExpertModel(FunctionModel):
    """Dummy function model that generates set of marks actions based on the number of messages."""

    def __init__(self) -> None:
        super().__init__(dummy_message_generator)
