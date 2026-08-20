"""Warmup manual-artifact behavior."""

from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

from gptnt.interactive.entrypoints.warmup_box import BoxWarmer
from gptnt.ktane.manuals.artifacts import ManualArtifact
from gptnt.players.action_predictor import ActionPredictor
from gptnt.players.input_builder import AgentInputBuilder
from gptnt.players.observation_handler import ObservationHandler
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol


@pytest.mark.anyio
async def test_warmup_seeds_the_explicit_manual_artifact(
    prepared_manual_artifact: ManualArtifact, mocker: MockerFixture
) -> None:
    capabilities = PlayerCapabilities(player_name="test-player", player_type="ai")
    protocol = PlayerProtocol(
        role="expert", communication_style="sync", is_playing_alone=False, include_manual=True
    )
    predictor = mocker.create_autospec(ActionPredictor, instance=True)
    predictor.send_request_to_agent.return_value = SimpleNamespace(
        output="OK", usage=None, raw_output="OK", ai_response_error=[]
    )
    warmer = BoxWarmer(
        capabilities=capabilities,
        observation_handler=mocker.create_autospec(ObservationHandler, instance=True),
        action_predictor=predictor,
        manual_artifact=prepared_manual_artifact,
    )
    _ = mocker.patch.object(
        AgentInputBuilder, "build_agent_input", new=mocker.AsyncMock(return_value="warmup input")
    )
    _ = mocker.patch.object(
        warmer, "generate_observations", return_value=(mocker.Mock(), mocker.Mock())
    )

    await warmer.run_prompt(protocol=protocol)

    conversation = predictor.configure_for_experiment.call_args.kwargs["conversation"]
    manual_request = conversation.entries[0].messages[0]
    assert "SHARED PREPARED MANUAL" in str(manual_request)
    predictor.send_request_to_agent.assert_awaited_once_with(message_input="warmup input")
