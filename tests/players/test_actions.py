from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pytest_cases import param_fixture, parametrize_with_cases

from gptnt.ktane.actions import GameActionType, RelativeCoordinate
from gptnt.players.actions import (
    DoNothingAction,
    DoNothingActionWithThoughts,
    InteractGameAction,
    InteractGameActionWithThoughts,
    PlayerOutputType,
    SendMessageAction,
    SendMessageActionWithThoughts,
)

game_command = param_fixture(
    "game_command", list(GameActionType), ids=[action.value for action in GameActionType]
)


class PlayerActionCases:
    def case_do_nothing(self) -> DoNothingAction:
        return DoNothingAction()

    def case_do_nothing_with_thoughts(self) -> DoNothingActionWithThoughts:
        return DoNothingActionWithThoughts(thoughts="Test thoughts")

    def case_send_message(self) -> SendMessageAction:
        return SendMessageAction(message="Test message")

    def case_send_message_with_thoughts(self) -> SendMessageActionWithThoughts:
        return SendMessageActionWithThoughts(message="Test message", thoughts="Test thoughts")

    def case_interact_set_of_marks(self, game_command: GameActionType) -> InteractGameAction[int]:
        return InteractGameAction[int](
            action=game_command,
            location=2 if game_command in GameActionType.require_location() else None,
        )

    def case_interact_relative_coordinate(
        self, game_command: GameActionType
    ) -> InteractGameAction[RelativeCoordinate]:
        return InteractGameAction[RelativeCoordinate](
            action=game_command,
            location=RelativeCoordinate(x_pos=0.5, y_pos=0.5)
            if game_command in GameActionType.require_location()
            else None,
        )

    def case_interact_set_of_marks_with_thoughts(
        self, game_command: GameActionType
    ) -> InteractGameActionWithThoughts[int]:
        return InteractGameActionWithThoughts[int](
            action=game_command,
            location=2 if game_command in GameActionType.require_location() else None,
            thoughts="Test thoughts",
        )

    def case_interact_relative_coordinate_with_thoughts(
        self, game_command: GameActionType
    ) -> InteractGameActionWithThoughts[RelativeCoordinate]:
        return InteractGameActionWithThoughts[RelativeCoordinate](
            action=game_command,
            location=RelativeCoordinate(x_pos=0.5, y_pos=0.5)
            if game_command in GameActionType.require_location()
            else None,
            thoughts="Test thoughts",
        )


@parametrize_with_cases("action", cases=PlayerActionCases)
def test_actions_are_parsed_correctly_from_json(action: PlayerOutputType) -> None:
    """Test that the actions are parsed correctly.

    This is a regression test to ensure that the actions are parsed correctly.
    """
    action_as_json = action.model_dump(mode="json", exclude_none=True, exclude_defaults=True)

    # Note: actions can be validated by their name or the value, so we check that too
    if isinstance(action, InteractGameAction):
        action_as_json["action"] = action.action.name

    test_model = Agent(TestModel(custom_output_args=action_as_json), output_type=action.__class__)
    output = test_model.run_sync("message")

    assert output.output == action
