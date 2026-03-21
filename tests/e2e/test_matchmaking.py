import pytest
from httpx import AsyncClient
from pytest_cases import fixture
from pytest_mock import MockerFixture

from gptnt.experiments.experiments import ExperimentSpec
from gptnt.services.experiment_manager.experiment_manager import ExperimentManager
from gptnt.services.game.service import GameService
from gptnt.services.player.service import PlayerService


@fixture
def experiment_spec() -> ExperimentSpec:
    return ExperimentSpec.model_validate_json(
        '{"mission_spec":{"seed":234,"timeLimit":60,"numStrikes":3,"components":["BigButton"],"optWidgets":1,"needyTime":60,"isFront":true,"timeScale":1.0,"timeStepSize":3000},"condition":"single_module","defuser_protocol":{"role":"defuser","communication_style":"sync","is_playing_alone":true,"include_manual":true,"thinking_framework":"act","allow_thoughts_output":false,"allow_thoughts_in_history":false,"allow_outputs_in_history":true,"receive_feedback_after_action":false,"allow_message_output":false},"defuser_name":"test-defuser","expert_protocol":null,"expert_name":null}'
    )


@pytest.mark.anyio
async def test_specs_can_be_added_via_endpoint(
    experiment_manager_app_client: AsyncClient,
    experiment_manager: ExperimentManager,
    experiment_spec: ExperimentSpec,
) -> None:
    # Ensure the spec is not already in the EM
    assert experiment_spec not in experiment_manager.specs

    # Add the spec via the endpoint
    _ = await experiment_manager_app_client.post(
        "/add-specs", json={"specs": [experiment_spec.model_dump(mode="json")]}
    )

    # Make sure it's in the EM
    assert experiment_spec in experiment_manager.specs


@pytest.mark.anyio
async def test_session_created_when_valid_match_exists(
    experiment_manager: ExperimentManager,
    game_service: GameService,
    defuser_player_service: PlayerService,
    experiment_spec: ExperimentSpec,
    mocker: MockerFixture,
) -> None:
    #  Mock `session.run` to not actually run the experiment
    _ = mocker.patch("gptnt.services.experiment_manager.session.Session.run", autospec=True)

    for game in experiment_manager.ready_games:
        if game.uuid == game_service.uuid:
            break
    else:
        pytest.fail("Game service UUID not found in EM ready games")

    for player in experiment_manager.ready_players:
        if player.uuid == defuser_player_service.uuid:
            break
    else:
        pytest.fail("Player service UUID not found in EM ready players")

    experiment_manager.specs.add(experiment_spec)
    await experiment_manager._try_match_experiments()

    assert len(experiment_manager._sessions) == 1, "Session was not created"
    assert not len(experiment_manager.ready_players)
    assert not len(experiment_manager.ready_games)
    session = next(iter(experiment_manager._sessions))

    assert session.defuser.uuid == defuser_player_service.uuid
    assert session.game.uuid == game_service.uuid
    assert session.spec == experiment_spec
