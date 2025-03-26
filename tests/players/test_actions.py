import pytest
from pytest_cases import parametrize_with_cases
from pytest_mock import MockerFixture

from gptnt.players.actions import DoNothingAction, SendMessageAction
from gptnt.players.expert import ExpertResultType
from gptnt.players.player import Player
from tests.players.fixtures import PlayerCases

ResultDataT = ExpertResultType


@pytest.mark.asyncio
@parametrize_with_cases("player", cases=PlayerCases)
async def test_do_nothing_action_goes_to_do_nothing_method(
    player: Player[None, ResultDataT], mocker: MockerFixture
) -> None:
    """Test that DoNothingAction handler actually does nothing."""
    # Make a spy to track the call to send_message
    spy = mocker.spy(player, "do_nothing_action")

    # create the action
    action = DoNothingAction()

    await player.direct_output_from_agent(action)

    assert spy.call_count == 1


@pytest.mark.asyncio
@parametrize_with_cases("player", cases=PlayerCases)
async def test_send_message_action_sends_message_to_dialogue_space(
    player: Player[None, ResultDataT], mocker: MockerFixture
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
