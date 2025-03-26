from typing import TypeVar

import pytest
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pytest_cases import parametrize_with_cases
from pytest_mock import MockerFixture

from gptnt.players.player import Player
from tests.players.fixtures import PlayerCases

ResultDataT = TypeVar("ResultDataT")


@pytest.mark.asyncio
@parametrize_with_cases("player", cases=PlayerCases)
async def test_connect_calls_dialogue_space(
    player: Player[None, ResultDataT], mocker: MockerFixture
) -> None:
    # Mock the connect return
    player.dialogue_space_client.connect = mocker.AsyncMock(return_value=None)
    # Verify the dialogue space client within the player is the same as the one passed
    await player.connect()
    assert player.dialogue_space_client.connect.await_count == 1


@pytest.mark.asyncio
@parametrize_with_cases("player", cases=PlayerCases)
@pytest.mark.skip("Not implemented")
async def test_run_once_calls_expected_methods(player: Player[None, ResultDataT]) -> None:
    raise NotImplementedError


@pytest.mark.asyncio
@parametrize_with_cases("player", cases=PlayerCases)
async def test_player_pulls_messages_from_dialogue_space(
    player: Player[None, ResultDataT], mocker: MockerFixture
) -> None:
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
) -> None:
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
) -> None:
    """Test behaviour when not connected to the dialogue space."""
    raise NotImplementedError


@pytest.mark.asyncio
@parametrize_with_cases("player", cases=PlayerCases)
async def test_usage_updates_correctly_after_run(
    player: Player[None, ResultDataT], mocker: MockerFixture
) -> None:
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


@pytest.mark.asyncio
@parametrize_with_cases("player", cases=PlayerCases)
async def test_message_history_updates_after_run(
    player: Player[None, ResultDataT], mocker: MockerFixture
) -> None:
    # Mock the pull for the dialogue space client
    player.dialogue_space_client.pull_messages = mocker.AsyncMock(
        return_value=["message1", "message2"]
    )

    assert player.usage.requests == 0
    assert player._message_history is None

    _ = await player.send_request_to_agent()

    assert player.usage.requests == 1
    assert player._message_history is not None


@pytest.mark.asyncio
@parametrize_with_cases("player", cases=PlayerCases)
async def test_message_history_resets_properly(
    player: Player[None, ResultDataT], mocker: MockerFixture
) -> None:
    """Test that the message history resets properly after a run.

    This means that after we reset, the message history should be None, and the return of the run
    should not include messages from the previous run.
    """
    # Mock the pull for the dialogue space client
    player.dialogue_space_client.pull_messages = mocker.AsyncMock(return_value=["message1"])

    _ = await player.send_request_to_agent()

    # Reset the message history
    player.reset_message_history()

    # Update the mock for the pull with a different message
    player.dialogue_space_client.pull_messages = mocker.AsyncMock(return_value=["message2"])

    # Run again
    _ = await player.send_request_to_agent()
    assert player._message_history is not None

    # Get the first message from the message history which uses a user prompt
    user_prompt = next(
        msg.parts[0]
        for msg in player._message_history
        if isinstance(msg, ModelRequest) and isinstance(msg.parts[0], UserPromptPart)
    )
    # Verify the content is only the second message and not the first one which came first
    assert isinstance(user_prompt, UserPromptPart)
    assert user_prompt.content == "message2"
    assert user_prompt.content != "message1"
