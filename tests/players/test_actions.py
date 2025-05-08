import itertools
from typing import get_args

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pytest_cases import param_fixture, parametrize_with_cases
from pytest_mock import MockerFixture

from gptnt.ktane.actions import GameActionType, RelativeCoordinate
from gptnt.players.actions import (
    BaseAction,
    DoNothingAction,
    InteractGameAction,
    InteractGameLocation,
    SendMessageAction,
)
from gptnt.players.ai.ai_player import AIPlayer
from gptnt.players.ai.defuser import DefuserOutputT
from gptnt.players.ai.expert import ExpertOutputT
from tests.players.fixtures import AIPlayerCases

OutputDataT = ExpertOutputT | DefuserOutputT[InteractGameLocation]


def test_all_actions_have_command_attribute() -> None:
    """Test that all actions have the command attribute."""
    # Pull all the action types from the `OutputDataT` union in this file
    commands = set(
        itertools.chain.from_iterable(
            [get_args(data_type.__value__) for data_type in get_args(OutputDataT)]
        )
    )
    for command in commands:
        assert "command" in command.model_fields


@pytest.mark.asyncio
@parametrize_with_cases("player", cases=AIPlayerCases)
async def test_do_nothing_action_goes_to_do_nothing_method(
    player: AIPlayer[None, OutputDataT], mocker: MockerFixture
) -> None:
    """Test that DoNothingAction handler actually does nothing."""
    # Make a spy to track the call to send_message
    spy = mocker.spy(player, "do_nothing_action")

    # create the action
    action = DoNothingAction()

    await player.direct_output_from_agent(action)

    assert spy.call_count == 1


@pytest.mark.asyncio
@parametrize_with_cases("player", cases=AIPlayerCases)
async def test_send_message_action_sends_message_to_dialogue_space(
    player: AIPlayer[None, OutputDataT], mocker: MockerFixture
) -> None:
    """Test that SendMessageAction handler sends message to dialogue space.

    We do not run the dialogue space server to check the messages are received, because that's
    checked by other tests
    """
    # Make a spy to track the call to send_message
    spy = mocker.spy(player.dialogue_space_client, "send_message")

    # create the action
    message_content = "Test message"
    action = SendMessageAction(message=message_content)

    await player.direct_output_from_agent(action)

    assert spy.call_count == 1
    assert spy.call_args[0][0] == message_content


game_command = param_fixture(
    "game_command", list(GameActionType), ids=[action.value for action in GameActionType]
)


class PlayerActionCases:
    def case_do_nothing(self) -> DoNothingAction:
        return DoNothingAction()

    def case_do_nothing_with_thoughts(self) -> DoNothingAction:
        return DoNothingAction(thoughts="Test thoughts")

    def case_send_message(self) -> SendMessageAction:
        return SendMessageAction(message="Test message")

    def case_send_message_with_thoughts(self) -> SendMessageAction:
        return SendMessageAction(message="Test message", thoughts="Test thoughts")

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
    ) -> InteractGameAction[int]:
        return InteractGameAction[int](
            action=game_command,
            location=2 if game_command in GameActionType.require_location() else None,
            thoughts="Test thoughts",
        )

    def case_interact_relative_coordinate_with_thoughts(
        self, game_command: GameActionType
    ) -> InteractGameAction[RelativeCoordinate]:
        return InteractGameAction[RelativeCoordinate](
            action=game_command,
            location=RelativeCoordinate(x_pos=0.5, y_pos=0.5)
            if game_command in GameActionType.require_location()
            else None,
            thoughts="Test thoughts",
        )


@parametrize_with_cases("action", cases=PlayerActionCases)
def test_actions_are_parsed_correctly_from_json(action: BaseAction) -> None:
    """Test that the actions are parsed correctly.

    This is a regression test to ensure that the actions are parsed correctly.
    """
    action_as_json = action.model_dump(
        mode="json", exclude={"command"}, exclude_none=True, exclude_defaults=True
    )

    # Note: actions can be validated by their name or the value, so we check that too
    if isinstance(action, InteractGameAction):
        action_as_json["action"] = action.action.name

    test_model = Agent(TestModel(custom_output_args=action_as_json), output_type=action.__class__)
    output = test_model.run_sync("message")

    assert output.output == action
