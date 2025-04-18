import itertools
from typing import get_args

import pytest
from pytest_cases import parametrize_with_cases
from pytest_mock import MockerFixture

from gptnt.players.actions import DoNothingAction, InteractGameLocation, SendMessageAction
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
