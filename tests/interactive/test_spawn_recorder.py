"""Unit tests for source-driven recorder selection in player spawn commands."""

from __future__ import annotations

import pytest

from gptnt.experiments.ledger.completion import Source
from gptnt.experiments.recorder.resolve import resolve_recorder
from gptnt.interactive.orchestration.spawn import _build_player_command
from gptnt.players.specification import PlayerSpec


@pytest.mark.parametrize("source", [Source.local, Source.wandb])
def test_build_player_command_selects_recorder_by_source(source: Source) -> None:
    command = _build_player_command(player=PlayerSpec(player="dummy"), source=source)

    assert f"player.experiment_recorder._target_={resolve_recorder(source)}" in command


def test_build_player_command_appends_provider_override_when_set() -> None:
    with_provider = _build_player_command(
        player=PlayerSpec(player="dummy", provider="openai"), source=Source.local
    )
    without_provider = _build_player_command(
        player=PlayerSpec(player="dummy"), source=Source.local
    )

    assert "player/provider=openai" in with_provider
    assert all(not arg.startswith("player/provider=") for arg in without_provider)
