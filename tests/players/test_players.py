from typing import Never, TypeVar

import pytest
from pytest_cases import parametrize_with_cases
from pytest_mock import MockerFixture

from gptnt.players.player import Player
from tests.players.fixtures import PlayerCases

ResultDataT = TypeVar("ResultDataT")


@pytest.mark.asyncio
@parametrize_with_cases("player", cases=PlayerCases)
async def test_connect_calls_dialogue_space(
    player: Player[None, ResultDataT], mocker: MockerFixture
) -> Never:
    # Mock the connect return
    player.dialogue_space_client.connect = mocker.AsyncMock(return_value=None)
    # Verify the dialogue space client within the player is the same as the one passed
    await player.connect()
    assert player.dialogue_space_client.connect.await_count == 1


@pytest.mark.asyncio
@parametrize_with_cases("player", cases=PlayerCases)
@pytest.mark.skip("Not implemented")
async def test_run_once_calls_expected_methods(player: Player[None, ResultDataT]) -> Never:
    raise NotImplementedError


@pytest.mark.asyncio
@parametrize_with_cases("player", cases=PlayerCases)
async def test_player_pulls_messages_from_dialogue_space(
    player: Player[None, ResultDataT], mocker: MockerFixture
) -> Never:
    """Test that `build_agent_input` pulls the messages from the dialogue space."""
    # Mock the pull for the dialogue space client
    player.dialogue_space_client.pull_messages = mocker.AsyncMock(
        return_value=["message1", "message2"]
    )

    # Pull and verify
    pulled_messages = await player.pull_unread_messages_from_dialogue_space()
    assert pulled_messages == "message1\nmessage2"


@pytest.mark.asyncio
@parametrize_with_cases("player", cases=PlayerCases)
@pytest.mark.skip("Not implemented")
async def test_build_agent_input_with_no_messages(
    player: Player[None, ResultDataT], mocker: MockerFixture
) -> Never:
    """Test behaviour when there are no messages in the dialogue space."""
    # TODO: when there are no messages, the input to the model should be empty?
    # Mock the pull for the dialogue space client
    player.dialogue_space_client.pull_messages = mocker.AsyncMock(return_value=[])

    # TODO: Pull and verify
    # pulled_messages = await player.pull_unread_messages_from_dialogue_space()
    raise NotImplementedError


@pytest.mark.asyncio
@parametrize_with_cases("player", cases=PlayerCases)
@pytest.mark.skip("Not implemented")
async def test_build_agent_input_with_disconnected_dialogue_space(
    player: Player[None, ResultDataT],
) -> Never:
    """Test behaviour when not connected to the dialogue space."""
    raise NotImplementedError


@pytest.mark.asyncio
@parametrize_with_cases("player", cases=PlayerCases)
async def test_usage_updates_correctly_after_run(
    player: Player[None, ResultDataT], mocker: MockerFixture
) -> Never:
    """Test that usage statistics update correctly after running the agent."""
    # Mock the pull for the dialogue space client
    player.dialogue_space_client.pull_messages = mocker.AsyncMock(
        return_value=["message1", "message2"]
    )

    assert player.usage.requests == 0

    _ = await player.send_request_to_agent()

    assert player.usage.requests == 1

    _ = await player.send_request_to_agent()
    assert player.usage.requests == 2
