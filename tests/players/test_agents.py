from pathlib import Path
from typing import get_args

import pytest
from pydantic_ai import BinaryContent, models
from pytest_cases import parametrize, parametrize_with_cases
from pytest_mock import MockerFixture

from gptnt.players.actions import (
    InteractGameAction,
    InteractGameLocation,
    SendMessageAction,
    SetOfMarksLocation,
)
from gptnt.players.ai.ai_player import NO_NEW_MESSAGES_SENTINEL, AIPlayer
from gptnt.players.ai.defuser import DefuserOutputT
from gptnt.players.ai.dummy import DummyDefuserModel, DummyExpertModel, actions_to_perform
from gptnt.players.ai.expert import ExpertOutputT
from gptnt.players.ai.prompts import BombStateMessage
from tests.players.fixtures import AIPlayerCases

OutputDataT = ExpertOutputT | DefuserOutputT[InteractGameLocation]

pytestmark = pytest.mark.asyncio
models.ALLOW_MODEL_REQUESTS = False


@parametrize_with_cases("player", cases=AIPlayerCases)
def test_provide_message_to_agent(player: AIPlayer[None, OutputDataT]) -> None:
    agent = player.agent

    message = "Test message"
    output = agent.run_sync(message)

    assert output


@parametrize_with_cases("player", cases=AIPlayerCases, glob="defuser_mdp_set_of_marks")
async def test_functional_model_does_not_crash(player: AIPlayer[None, OutputDataT]) -> None:
    for _ in range(30):
        with player.agent.override(model=DummyDefuserModel()):
            response = await player.send_request_to_agent()

            assert response
            assert isinstance(response, InteractGameAction[SetOfMarksLocation])
    player.reset_message_history()

    with player.agent.override(model=DummyDefuserModel()):
        response = await player.send_request_to_agent()
        assert response == actions_to_perform[0]


@parametrize_with_cases("player", cases=AIPlayerCases, glob="expert")
@parametrize("bomb_state_message", list(get_args(BombStateMessage)))
async def test_dummy_expert_handles_reflection_message(
    player: AIPlayer[None, OutputDataT],
    bomb_state_message: BombStateMessage,
    mocker: MockerFixture,
) -> None:
    # mock receiving the bomb state as a message
    player.pull_unread_messages_from_dialogue_space = mocker.AsyncMock()
    player.pull_unread_messages_from_dialogue_space.return_value = bomb_state_message

    with player.agent.override(model=DummyExpertModel()):
        response = await player.handle_reflection_prompt()

    assert response is not None
    assert response.message == bomb_state_message


@parametrize_with_cases("player", cases=AIPlayerCases, glob="defuser_mdp_set_of_marks")
@parametrize("bomb_state_message", list(get_args(BombStateMessage)))
async def test_dummy_defuser_handles_reflection_message(
    player: AIPlayer[None, OutputDataT],
    bomb_state_message: BombStateMessage,
    mocker: MockerFixture,
) -> None:
    # mock receiving the bomb state as a message
    player.pull_unread_messages_from_dialogue_space = mocker.AsyncMock()
    player.pull_unread_messages_from_dialogue_space.return_value = bomb_state_message

    with player.agent.override(model=DummyDefuserModel()):
        response = await player.handle_reflection_prompt()

    assert response is not None
    assert response.message == bomb_state_message


@parametrize_with_cases("player", cases=AIPlayerCases)
async def test_dummy_models_handle_no_reflection_message(
    player: AIPlayer[None, OutputDataT], mocker: MockerFixture
) -> None:
    # mock receiving the bomb state as a message
    player.pull_unread_messages_from_dialogue_space = mocker.AsyncMock()
    player.pull_unread_messages_from_dialogue_space.return_value = NO_NEW_MESSAGES_SENTINEL

    with player.agent.override(model=DummyDefuserModel()):
        response = await player.handle_reflection_prompt()

        assert response is None


@parametrize_with_cases("player", cases=AIPlayerCases, glob="expert")
async def test_context_length_resets_properly_for_expert(
    player: AIPlayer[None, OutputDataT], mocker: MockerFixture
) -> None:
    with player.agent.override(model=DummyExpertModel()):
        # get the prompt first since it can be huge
        response = await player.send_request_to_agent()

        # Prevent the context length from being above the first message
        player.player_usage.truncation_threshold = 1
        player.usage_limits.total_tokens_limit = player.player_usage.context_length + 1

        player.build_agent_input = mocker.AsyncMock()
        player.build_agent_input.return_value = "first"
        for _ in range(100):
            response = await player.send_request_to_agent()
            assert isinstance(response, SendMessageAction)
            player.build_agent_input.return_value = response.message

    assert player.player_usage.num_times_truncated == 100
    assert all(request_tokens > 0 for request_tokens in player.player_usage.request_tokens)
    assert all(response_tokens > 0 for response_tokens in player.player_usage.response_tokens)


@pytest.fixture(scope="session")
def binary_image_content(fixture_path: Path) -> BinaryContent:
    """Fixture to provide a screenshot."""
    image_bytes = fixture_path.joinpath("screenshot.png").read_bytes()
    return BinaryContent(data=image_bytes, media_type="image/png")


@parametrize_with_cases("player", cases=AIPlayerCases, glob="defuser_mdp_set_of_marks")
@pytest.mark.skip(reason="I don't know how to test this and I don't trust this.")
async def test_context_length_resets_properly_for_defuser(
    player: AIPlayer[None, OutputDataT], mocker: MockerFixture, binary_image_content: BinaryContent
) -> None:
    with player.agent.override(model=DummyDefuserModel()):
        player.build_agent_input = mocker.AsyncMock()
        player.build_agent_input.return_value = [
            *[binary_image_content for _ in range(player.player_usage.num_images_per_message)],
            "this is the first message and is going to be the only message in the defuser so lets make it a bit bigger",
        ]
        player.player_usage.tokens_per_image = 451133

        # get the prompt first since it can be huge
        _ = await player.send_request_to_agent()

        # Prevent the context length from being above the first message
        player.usage_limits.total_tokens_limit = player.player_usage.context_length + 1
        player.player_usage.truncation_threshold = 1

        for idx in range(100):
            player.build_agent_input.return_value = [
                *[binary_image_content for _ in range(player.player_usage.num_images_per_message)],
                f"message {idx}",
            ]
            _ = await player.send_request_to_agent()
            assert all(request_tokens > 0 for request_tokens in player.player_usage.request_tokens)

    assert player.player_usage.num_times_truncated == 100
