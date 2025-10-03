import uuid

import pytest
from httpx import AsyncClient
from pydantic_ai.exceptions import AgentRunError
from pytest_cases import fixture
from pytest_mock import MockerFixture

from gptnt.experiments.experiments import ExperimentSpec
from gptnt.players.actions import NO_NEW_MESSAGES_SENTINEL
from gptnt.services.events.player import PlayerState
from gptnt.services.experiment_descriptor import ExperimentDescriptor
from gptnt.services.player.client import PlayerClient
from gptnt.services.player.supervisor import PlayerSupervisor

pytestmark = pytest.mark.anyio


@fixture
async def defuser_player_client(
    defuser_player_app_client: AsyncClient, mocker: MockerFixture
) -> PlayerClient:
    client = PlayerClient()
    client._client = defuser_player_app_client
    client.recreate_client = mocker.Mock(return_value=defuser_player_app_client)
    return client


@fixture
async def fake_experiment_descriptor(
    experiment_spec: ExperimentSpec, defuser_player_supervisor: PlayerSupervisor
) -> ExperimentDescriptor:
    """An experiment descriptor that doens't spawn a game service too."""
    return ExperimentDescriptor(
        experiment_spec=experiment_spec,
        session_id=uuid.uuid4(),
        defuser_uuid=defuser_player_supervisor.uuid,
        defuser_url=defuser_player_supervisor.url,
        game_uuid=uuid.uuid4(),
        game_url="",
        expert_url=None,
        expert_uuid=None,
    )


@fixture
async def configured_player(
    defuser_player_client: PlayerClient,
    fake_experiment_descriptor: ExperimentDescriptor,
    defuser_player_supervisor: PlayerSupervisor,
) -> tuple[PlayerClient, PlayerSupervisor]:
    _ = await defuser_player_client.configure_player(
        player_protocol=fake_experiment_descriptor.experiment_spec.defuser_protocol,
        experiment_descriptor=fake_experiment_descriptor,
    )
    return defuser_player_client, defuser_player_supervisor


async def test_player_service_can_be_configured_over_api(
    fake_experiment_descriptor: ExperimentDescriptor,
    defuser_player_client: PlayerClient,
    defuser_player_supervisor: PlayerSupervisor,
) -> None:
    _ = await defuser_player_client.configure_player(
        player_protocol=fake_experiment_descriptor.experiment_spec.defuser_protocol,
        experiment_descriptor=fake_experiment_descriptor,
    )

    # Make sure the defuser has the correct specs
    assert (
        defuser_player_supervisor.protocol
        == fake_experiment_descriptor.experiment_spec.defuser_protocol
    )
    assert defuser_player_supervisor.experiment_descriptor == fake_experiment_descriptor
    assert defuser_player_supervisor.state == PlayerState.waiting_for_turn


async def test_player_service_resets_properly_from_api_call(
    configured_player: tuple[PlayerClient, PlayerSupervisor],
) -> None:
    defuser_player_client, defuser_player_supervisor = configured_player

    # Call reset and make sure it works
    assert defuser_player_supervisor.state > PlayerState.idle
    _ = await defuser_player_client.reset_player()
    assert defuser_player_supervisor.state == PlayerState.idle


@pytest.mark.skip
async def test_player_does_not_hang_when_ai_times_out(
    configured_player: tuple[PlayerClient, PlayerSupervisor], mocker: MockerFixture
) -> None:
    defuser_player_client, defuser_player_supervisor = configured_player
    _ = mocker.Mock(
        defuser_player_supervisor.action_predictor.agent.run, side_effect=AgentRunError
    )
    _ = await defuser_player_client.forward_pass()

    assert defuser_player_supervisor.state == PlayerState.idle


async def test_sent_message_goes_to_message_manager(
    configured_player: tuple[PlayerClient, PlayerSupervisor],
) -> None:
    defuser_player_client, defuser_player_supervisor = configured_player
    assert defuser_player_supervisor.message_manager.pull_messages() == NO_NEW_MESSAGES_SENTINEL

    # one message
    _ = await defuser_player_client.send_message("message_one")
    assert defuser_player_supervisor.message_manager._unpulled_messages[-1] == "message_one"
    assert defuser_player_supervisor.message_manager.pull_messages() == "message_one"
    assert len(defuser_player_supervisor.message_manager._unpulled_messages) == 0

    _ = await defuser_player_client.send_message("message_two")
    _ = await defuser_player_client.send_message("message_three")
    assert defuser_player_supervisor.message_manager._unpulled_messages[-2] == "message_two"
    assert defuser_player_supervisor.message_manager._unpulled_messages[-1] == "message_three"
    assert (
        defuser_player_supervisor.message_manager.pull_messages() == "message_two\nmessage_three"
    )
    assert len(defuser_player_supervisor.message_manager._unpulled_messages) == 0


async def test_sent_feedback_messages_goes_to_message_manager(
    configured_player: tuple[PlayerClient, PlayerSupervisor],
) -> None:
    defuser_player_client, defuser_player_supervisor = configured_player
    _ = await defuser_player_client.send_feedback("feedback_one")
    assert defuser_player_supervisor.message_manager._unpulled_messages[-1] == "feedback_one"
    assert defuser_player_supervisor.message_manager.pull_messages() == "feedback_one"
    assert len(defuser_player_supervisor.message_manager._unpulled_messages) == 0


async def test_sent_feedback_messages_interleave_sent_messages(
    configured_player: tuple[PlayerClient, PlayerSupervisor],
) -> None:
    defuser_player_client, defuser_player_supervisor = configured_player
    _ = await defuser_player_client.send_feedback("feedback_one")
    _ = await defuser_player_client.send_message("message_one")
    assert defuser_player_supervisor.message_manager._unpulled_messages[-2] == "feedback_one"
    assert defuser_player_supervisor.message_manager._unpulled_messages[-1] == "message_one"
    assert defuser_player_supervisor.message_manager.pull_messages() == "feedback_one\nmessage_one"
    assert len(defuser_player_supervisor.message_manager._unpulled_messages) == 0


async def test_reflection_request_works(
    configured_player: tuple[PlayerClient, PlayerSupervisor],
) -> None:
    defuser_player_client, defuser_player_supervisor = configured_player

    assert len(defuser_player_supervisor.episode_tracker.reflections) == 0

    response = await defuser_player_client.send_reflection_request(
        reflection_message="terminated-defused"
    )
    assert response.status_code == 200
    assert len(defuser_player_supervisor.episode_tracker.reflections) == 1


async def test_stop_player_works(
    configured_player: tuple[PlayerClient, PlayerSupervisor], mocker: MockerFixture
) -> None:
    defuser_player_client, defuser_player_supervisor = configured_player

    # Set up spys
    reset_spy = mocker.spy(defuser_player_supervisor, "reset")
    tracker_spy = mocker.spy(defuser_player_supervisor.episode_tracker, "on_experiment_stop")

    # Check the player state before calling stop
    assert defuser_player_supervisor.state == PlayerState.waiting_for_turn

    # call the endpoint
    response = await defuser_player_client.stop_player()
    # Ensure that it returns a 202
    assert response.status_code == 202

    _ = reset_spy.assert_called()
    _ = tracker_spy.assert_awaited()

    assert defuser_player_supervisor.state == PlayerState.idle
