"""Player-service manual artifact behavior."""

import pytest
from pytest_mock import MockerFixture

from gptnt.interactive.entrypoints.run_player import main as build_player_app
from gptnt.interactive.services.player.service import _ConfigureExperimentPayload
from gptnt.ktane.manuals.artifacts import ManualArtifact

from tests._factories.experiments import make_experiment_instance, make_provenance


@pytest.mark.anyio
async def test_no_manual_player_does_not_load_an_artifact(mocker: MockerFixture) -> None:
    """Configure a no-manual player without selecting or reading an artifact."""
    player_app = build_player_app(hydra_overrides=["player=test-defuser"])
    player_service = player_app.context.get("player_service")
    assert player_service is not None

    _ = mocker.patch.object(
        ManualArtifact,
        "load",
        side_effect=AssertionError("a no-manual player must not load an artifact"),
    )
    _ = mocker.patch.object(
        player_service.experiment_recorder, "configure_for_experiment", new=mocker.AsyncMock()
    )
    _ = mocker.patch.object(
        player_service.incoming_message_handler, "start_subscriber", new=mocker.AsyncMock()
    )
    instance = make_experiment_instance()

    configured = await player_service.configure_for_experiment(
        _ConfigureExperimentPayload(
            protocol=instance.defuser_protocol,
            experiment_instance=instance,
            provenance=make_provenance(),
        )
    )

    assert configured
    assert not player_service.conversation.entries
