from __future__ import annotations

from typing import TYPE_CHECKING

from gptnt.experiments.spec import load_specs_from_dir, write_specs_to_dir
from gptnt.experiments.suite.compose import compose_suite
from gptnt.experiments.suite.generate import generate_specs

from tests._factories.experiments import make_experiment_spec

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_write_then_load_preserves_frozen_suite_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A generated spec keeps its frozen digest after the live mission contents change."""
    specs = generate_specs(["suites=single-solo-player-sync", "players.all=[test-defuser]"])
    spec = specs[0]
    out = tmp_path / "my-run"

    written = write_specs_to_dir([spec], out)

    live_suite = compose_suite(spec.suite_name)
    changed_missions = [
        mission.model_copy(update={"seed": mission.seed + 1})
        for mission in live_suite.loaded_missions
    ]

    monkeypatch.setattr(
        "gptnt.experiments.suite.core.load_missions", lambda _path: changed_missions
    )
    assert live_suite.suite_digest != spec.suite_digest

    assert written == [out / f"{spec.attempt_name}.json"]
    loaded = load_specs_from_dir(out)
    assert loaded == [spec]


def test_load_from_missing_dir_is_empty(tmp_path: Path) -> None:
    """An absent spec dir yields no specs (the caller turns this into a clear 'generate first')."""
    assert load_specs_from_dir(tmp_path / "never-generated") == []


def test_hand_editing_a_spec_set_is_picked_up(tmp_path: Path) -> None:
    """Deleting a spec file (e.g. splitting work across machines) shrinks what loads back."""
    specs = [
        make_experiment_spec(seed=1),
        make_experiment_spec(seed=2),
        make_experiment_spec(seed=3),
    ]
    out = tmp_path / "my-run"
    written = write_specs_to_dir(specs, out)

    written[0].unlink()  # drop one spec, as a multi-machine split would

    loaded = load_specs_from_dir(out)
    assert len(loaded) == 2
    assert specs[0] not in loaded
