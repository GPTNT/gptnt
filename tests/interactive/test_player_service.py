"""Player-service manual artifact behavior."""

from pathlib import Path

import orjson
import pytest
from pytest_mock import MockerFixture

from gptnt.common.runtime_settings import MANUAL_ARTIFACTS_ENV
from gptnt.interactive.entrypoints.run_player import main as build_player_app
from gptnt.interactive.services.player.service import _ConfigureExperimentPayload
from gptnt.ktane.manuals.artifacts import ManualArtifact
from gptnt.ktane.manuals.requirement import ManualRequirement
from gptnt.players.specification import PlayerProtocol

from tests._factories.experiments import (
    make_experiment_instance,
    make_experiment_spec,
    make_provenance,
)
from tests._factories.manuals import make_compiled_manual


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


@pytest.mark.anyio
async def test_manual_player_loads_the_artifact_for_its_mission_rule_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """Use the seeded requirement key instead of a profile-only artifact lookup."""
    protocol = PlayerProtocol(
        role="defuser", communication_style="sync", is_playing_alone=True, include_manual=True
    )
    base_spec = make_experiment_spec()
    spec = base_spec.model_copy(
        update={
            "mission_spec": base_spec.mission_spec.model_copy(update={"rule_seed": 7}),
            "defuser_protocol": protocol,
        }
    )
    instance = make_experiment_instance(spec)
    artifact = make_compiled_manual(tmp_path, name="seeded", text="RULE SEED SEVEN")
    requirement = ManualRequirement(profile=instance.manual_profile, rule_seed=7)
    monkeypatch.setenv(
        MANUAL_ARTIFACTS_ENV, orjson.dumps({requirement.runtime_key: str(artifact.path)}).decode()
    )
    player_app = build_player_app(hydra_overrides=["player=test-defuser"])
    player_service = player_app.context.get("player_service")
    assert player_service is not None

    load = mocker.patch.object(ManualArtifact, "load", return_value=artifact)
    _ = mocker.patch.object(
        player_service.experiment_recorder, "configure_for_experiment", new=mocker.AsyncMock()
    )
    _ = mocker.patch.object(
        player_service.incoming_message_handler, "start_subscriber", new=mocker.AsyncMock()
    )

    configured = await player_service.configure_for_experiment(
        _ConfigureExperimentPayload(
            protocol=protocol, experiment_instance=instance, provenance=make_provenance()
        )
    )

    assert configured
    load.assert_called_once_with(artifact.path)
