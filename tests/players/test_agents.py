from typing import get_args

import pytest
from pydantic_ai import models
from pytest_cases import parametrize, parametrize_with_cases
from pytest_mock import MockerFixture

from gptnt.players.actions import InteractGameAction, InteractGameLocation, SetOfMarksLocation
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
