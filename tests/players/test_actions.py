import itertools
from typing import Union, get_args

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


def test_all_actions_have_action_type_attribute() -> None:
    """Test that all actions have the action_type attribute."""
    # Pull all the action types from the `OutputDataT` union in this file
    action_types = set(
        itertools.chain.from_iterable(
            [get_args(data_type.__value__) for data_type in get_args(OutputDataT)]
        )
    )
    for action_type in action_types:
        assert "action_type" in action_type.model_fields


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


game_action_type = param_fixture(
    "game_action_type", list(GameActionType), ids=[action.value for action in GameActionType]
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

    def case_interact_set_of_marks(
        self, game_action_type: GameActionType
    ) -> InteractGameAction[int]:
        return InteractGameAction[int](
            action=game_action_type,
            location=2 if game_action_type in GameActionType.require_location() else None,
        )

    def case_interact_relative_coordinate(
        self, game_action_type: GameActionType
    ) -> InteractGameAction[RelativeCoordinate]:
        return InteractGameAction[RelativeCoordinate](
            action=game_action_type,
            location=RelativeCoordinate(x_pos=0.5, y_pos=0.5)
            if game_action_type in GameActionType.require_location()
            else None,
        )

    def case_interact_set_of_marks_with_thoughts(
        self, game_action_type: GameActionType
    ) -> InteractGameAction[int]:
        return InteractGameAction[int](
            action=game_action_type,
            location=2 if game_action_type in GameActionType.require_location() else None,
            thoughts="Test thoughts",
        )

    def case_interact_relative_coordinate_with_thoughts(
        self, game_action_type: GameActionType
    ) -> InteractGameAction[RelativeCoordinate]:
        return InteractGameAction[RelativeCoordinate](
            action=game_action_type,
            location=RelativeCoordinate(x_pos=0.5, y_pos=0.5)
            if game_action_type in GameActionType.require_location()
            else None,
            thoughts="Test thoughts",
        )


@parametrize_with_cases("action", cases=PlayerActionCases)
@pytest.mark.skip(reason="I don't understand pydantic-ai yet")
def test_actions_are_parsed_correctly_from_json(action: BaseAction) -> None:
    """Test that the actions are parsed correctly.

    This is a regression test to ensure that the actions are parsed correctly.
    """
    action_as_json = action.model_dump(mode="json")
    test_model = Agent(
        TestModel(custom_output_args=action_as_json),
        output_type=Union[  # noqa: UP007
            DoNothingAction,
            SendMessageAction,
            InteractGameAction[RelativeCoordinate],
            InteractGameAction[int],
        ],
    )

    output = test_model.run_sync("message")

    assert isinstance(output.output, action.__class__)
