"""Round-trip tests for the on-disk spec store shared by `generate`, `run` and `submit`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gptnt.experiments.spec import ExperimentSpec
from gptnt.experiments.specs_store import load_specs_from_dir, write_specs_to_dir
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.specification import PlayerProtocol

if TYPE_CHECKING:
    from pathlib import Path


def _spec(seed: int) -> ExperimentSpec:
    """A real single-player ExperimentSpec; the seed makes each attempt_name distinct."""
    return ExperimentSpec(
        mission_spec=KtaneMissionSpec(
            seed=seed,
            time_limit=300,
            num_strikes_allowed=3,
            components=["Wires"],
            optional_widgets=1,
            needy_time=60,
        ),
        mission_set="single_module",
        defuser_protocol=PlayerProtocol(
            role="defuser",
            communication_style="sync",
            is_playing_alone=True,
            include_manual=False,
            receive_feedback_after_action=False,
            allow_magic_actions=False,
        ),
        defuser_name="test-defuser",
        expert_protocol=None,
        expert_name=None,
    )


def test_write_then_load_round_trips_specs(tmp_path: Path) -> None:
    """Specs written to a dir load back identically, one JSON file per spec by attempt_name."""
    specs = [_spec(1), _spec(2), _spec(3)]
    out = tmp_path / "my-run"

    written = write_specs_to_dir(specs, out)

    assert len(written) == 3
    assert {path.name for path in written} == {f"{spec.attempt_name}.json" for spec in specs}
    loaded = load_specs_from_dir(out)
    assert loaded == specs


def test_load_from_missing_dir_is_empty(tmp_path: Path) -> None:
    """An absent spec dir yields no specs (the caller turns this into a clear 'generate first')."""
    assert load_specs_from_dir(tmp_path / "never-generated") == []


def test_hand_editing_a_spec_set_is_picked_up(tmp_path: Path) -> None:
    """Deleting a spec file (e.g. splitting work across machines) shrinks what loads back."""
    specs = [_spec(1), _spec(2), _spec(3)]
    out = tmp_path / "my-run"
    written = write_specs_to_dir(specs, out)

    written[0].unlink()  # drop one spec, as a multi-machine split would

    loaded = load_specs_from_dir(out)
    assert len(loaded) == 2
    assert specs[0] not in loaded
