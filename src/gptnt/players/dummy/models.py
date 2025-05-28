from contextlib import suppress

import structlog
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from gptnt.ktane.actions import GameActionType
from gptnt.players.actions import InteractGameAction, SendMessageAction, SetOfMarksLocation

# from gptnt.players.prompts import BombStateMessage

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


def check_for_reflection_message(messages: list[ModelMessage]) -> str | None:  # noqa: WPS218
    """Check if the last message is a reflection message.

    Theres a lot of indexing here...
    """
    with suppress(AssertionError):
        assert isinstance(messages[-1], ModelRequest)  # noqa: WPS204
        assert isinstance(messages[-1].parts, list)
        assert isinstance(messages[-1].parts[0], UserPromptPart)
        assert isinstance(messages[-1].parts[0].content, list)
        expected_reflection_message = messages[-1].parts[0].content[0]  # noqa: WPS219
        # assert expected_reflection_message in get_args(BombStateMessage)
        assert isinstance(expected_reflection_message, str)
        return expected_reflection_message

    return None


def dummy_message_generator(
    messages: list[ModelMessage],
    info: AgentInfo,  # noqa: WPS110 ARG001
) -> ModelResponse:
    """Dummy function model that generates set of marks actions based on the number of messages."""
    # if reflection_message := check_for_reflection_message(messages):  # noqa: WPS332
    #     # If we get a reflection message, we need to send it back
    #     logger.info("Sending reflection message", message=reflection_message)
    #     return ModelResponse(
    #         parts=[
    #             ToolCallPart(
    #                 "final_result_SendMessageAction",
    #                 SendMessageAction(message=reflection_message).model_dump(
    #                     exclude={"thoughts", "command"}, mode="json"
    #                 ),
    #             )
    #         ]
    #     )

    message = SendMessageAction(message=f"Message {len(messages)}")
    return ModelResponse(
        parts=[
            ToolCallPart(
                "final_result_SendMessageAction",
                message.model_dump(exclude={"thoughts", "command"}, mode="json"),
            )
        ]
    )


class DummyDefuserFunction:
    """Dummy defuser function for the dummy defuser model, but the actions also reset."""

    __name__ = "dummy_defuser_function"

    def __init__(self) -> None:
        self.actions_to_perform = iter(actions_to_perform)

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:  # noqa: WPS110, ARG002
        """Run the dummy defuser function."""
        if len(messages) < 2:  # noqa: PLR2004
            # Assume that it's a new game and reset it
            self.actions_to_perform = iter(actions_to_perform)

        # with suppress(ValueError):
        #     return self._maybe_send_reflection_message(messages, info)

        try:
            action_to_perform = next(self.actions_to_perform)
        except StopIteration:
            # If we run out of actions, just return a click release action
            logger.warning("Ran out of actions to perform, returning click release action.")
            action_to_perform = SoMAction(action=GameActionType.click_release, location="A")

        model_response = action_to_perform.model_dump(mode="json", exclude={"thoughts", "command"})
        model_response["action"] = action_to_perform.action.name

        logger.info("Sending action", action=model_response)
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "final_result_InteractGameAction[SingleAlphabetLetter]", model_response
                )
            ]
        )

    # def _maybe_send_reflection_message(
    #     self,
    #     messages: list[ModelMessage],
    #     info: AgentInfo,  # noqa: WPS110
    # ) -> ModelResponse:
    #     """Send a reflection message if needed."""
    #     if reflection_message := check_for_reflection_message(messages):  # noqa: WPS332
    #         # If we get a reflection message, we need to send it back
    #         logger.info("Sending reflection message", message=reflection_message)
    #         return ModelResponse(
    #             parts=[
    #                 ToolCallPart(
    #                     "final_result",
    #                     {
    #                         "response": SendMessageAction(message=reflection_message).model_dump(
    #                             exclude={"thoughts", "command"}, mode="json"
    #                         )
    #                     },
    #                 )
    #             ]
    #         )
    #     raise ValueError("no reflection message found")


class DummyDefuserModel(FunctionModel):
    """Dummy function model that generates set of marks actions based on the number of messages."""

    def __init__(self) -> None:
        super().__init__(DummyDefuserFunction())


class DummyExpertModel(FunctionModel):
    """Dummy function model that generates set of marks actions based on the number of messages."""

    def __init__(self) -> None:
        super().__init__(dummy_message_generator)
