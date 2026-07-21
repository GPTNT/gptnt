"""Unit tests for source-driven recorder selection in player spawn commands."""

from __future__ import annotations

from gptnt.experiments.ledger.base import Source
from gptnt.experiments.recorder.local import ExperimentPlayerRecorder
from gptnt.experiments.recorder.resolve import resolve_recorder
from gptnt.experiments.recorder.wandb import WandbExperimentPlayerRecorder
from gptnt.interactive.orchestration.spawn import _build_player_command
from gptnt.players.specification import PlayerSpec


def test_resolve_recorder_local_targets_local_recorder() -> None:
    target = resolve_recorder(Source.local)

    assert target == "gptnt.experiments.recorder.local.ExperimentPlayerRecorder"
    module, _, qualname = target.rpartition(".")
    assert module == ExperimentPlayerRecorder.__module__
    assert qualname == ExperimentPlayerRecorder.__qualname__


def test_resolve_recorder_wandb_targets_wandb_recorder() -> None:
    target = resolve_recorder(Source.wandb)

    assert target == "gptnt.experiments.recorder.wandb.WandbExperimentPlayerRecorder"
    module, _, qualname = target.rpartition(".")
    assert module == WandbExperimentPlayerRecorder.__module__
    assert qualname == WandbExperimentPlayerRecorder.__qualname__


def test_build_player_command_overrides_hydra_target_key() -> None:
    command = _build_player_command(player=PlayerSpec(player="dummy"), source=Source.local)

    # The override MUST use hydra's `_target_` key (trailing underscore); `_target` is silently
    # ignored by `hydra.utils.instantiate`, which would leave the config default in place.
    assert f"player.experiment_recorder._target_={resolve_recorder(Source.local)}" in command


def test_build_player_command_selects_recorder_by_source() -> None:
    wandb_command = _build_player_command(player=PlayerSpec(player="dummy"), source=Source.wandb)

    assert f"player.experiment_recorder._target_={resolve_recorder(Source.wandb)}" in wandb_command


def test_build_player_command_appends_provider_override_when_set() -> None:
    with_provider = _build_player_command(
        player=PlayerSpec(player="dummy", provider="openai"), source=Source.local
    )
    without_provider = _build_player_command(
        player=PlayerSpec(player="dummy"), source=Source.local
    )

    assert "player/provider=openai" in with_provider
    assert all(not arg.startswith("player/provider=") for arg in without_provider)
