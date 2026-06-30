"""The W&B-optional commands, exercised through the CLI runner with the local source.

These pin the user-visible behaviour that makes the benchmark runnable without a W&B account:
`status` reports completion from disk, `submit` skips already-done specs from disk, and
`cleanup-outputs` prunes invalid local files and orphaned `.tmp` writes (preview by default,
deleting only with `--execute`). They run with no W&B configured.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from gptnt.cli.__main__ import build_app
from gptnt.experiments.ledger.base import Source
from gptnt.experiments.ledger.resolve import filter_experiments
from gptnt.experiments.recorder.parquet import (
    RecordFooter,
    build_footer,
    write_player_record_parquet,
)
from gptnt.ktane.state.bomb import BombState

from tests._cli_runner import invoke_cli
from tests._factories.experiments import make_experiment_descriptor, make_experiment_spec

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.experiments.spec import ExperimentSpec


def _write_record(
    output_dir: Path, spec: ExperimentSpec, *, final_bomb_state: BombState | None, crash: bool
) -> Path:
    """Write a parquet record whose footer carries the spec's outcome the ledger/cleanup read.

    The attempt name lives only in the footer descriptor (built from `spec`), not the filename, so
    these exercises prove the ledger/cleanup key off the footer.
    """
    footer_model = RecordFooter(
        descriptor=make_experiment_descriptor(spec),
        final_bomb_state=final_bomb_state,
        is_hard_crash=crash,
        role="defuser",
    )
    footer = build_footer(footer_model, player_uuid=str(uuid4()))
    path = output_dir / f"experiment-{uuid4()}.parquet"
    write_player_record_parquet(blobbed_steps=[], footer=footer, output_path=path)
    return path


def _completed_bomb_state() -> BombState:
    """A bomb whose modules are all solved (a valid, completed ending)."""
    return BombState.model_validate(
        {
            "seed": 1,
            "maxStrikes": 3,
            "strikes": None,
            "isDetonated": False,
            "isSolved": True,
            "isLightOn": True,
            "bombSide": "front",
            "timerModule": {
                "name": "Timer",
                "onFront": True,
                "index": 0,
                "secondsRemaining": 50.0,
            },
            "widgets": [],
            "modules": [],
        }
    )


def _write_completed_output(output_dir: Path, spec: ExperimentSpec) -> Path:
    """Write a recorded output that reached a valid, completed bomb state."""
    return _write_record(output_dir, spec, final_bomb_state=_completed_bomb_state(), crash=False)


def test_filter_experiments_drops_only_the_done_ones(tmp_path: Path) -> None:
    done, todo = make_experiment_spec(seed=1), make_experiment_spec(seed=2)
    _ = _write_completed_output(tmp_path, done)

    remaining = filter_experiments([done, todo], source=Source.local, output_dir=tmp_path)

    assert remaining == [todo]


def test_status_reports_disk_completion(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    done = make_experiment_spec(seed=1)
    _ = _write_completed_output(output_dir, done)

    # The status command reads its "expected" names from a dir of `<attempt_name>.json` files.
    expected_dir = tmp_path / "expected"
    expected_dir.mkdir()
    for name in (done.attempt_name, "todo-exp"):
        _ = (expected_dir / f"{name}.json").write_text("{}")

    result = invoke_cli(
        build_app(), ["status", str(expected_dir), "--output-dir", str(output_dir)]
    )

    assert result.exit_code == 0, result.output
    # The full attempt name is long and the status table truncates the tail, so assert on the
    # front of the name (the suite it belongs to) plus the counts that prove it matched by name.
    assert "single-parametric-sync" in result.output
    assert "1 done" in result.output
    assert "1 not attempted" in result.output


def test_cleanup_local_prunes_invalid_outputs(tmp_path: Path) -> None:
    kept = _write_completed_output(tmp_path, make_experiment_spec(seed=1))
    crashed = _write_record(
        tmp_path, make_experiment_spec(seed=2), final_bomb_state=None, crash=True
    )

    result = invoke_cli(build_app(), ["cleanup-outputs", str(tmp_path), "--execute"])

    assert result.exit_code == 0, result.output
    assert not crashed.exists()
    assert kept.exists()


def test_cleanup_local_previews_by_default(tmp_path: Path) -> None:
    kept = _write_completed_output(tmp_path, make_experiment_spec(seed=1))
    crashed = _write_record(
        tmp_path, make_experiment_spec(seed=2), final_bomb_state=None, crash=True
    )

    result = invoke_cli(build_app(), ["cleanup-outputs", str(tmp_path)])

    assert result.exit_code == 0, result.output
    # Default is a dry run: nothing is deleted and the crashed file is named as a delete candidate.
    assert crashed.exists()
    assert kept.exists()
    # The summary verb stays conditional ("would delete") and each candidate is marked. Paths wrap
    # across lines in the rendered output, so assert on the stable markers, not the full path.
    assert "[To Delete]" in result.output
    assert "would delete 1 invalid" in result.output


def test_cleanup_local_removes_orphaned_tmp(tmp_path: Path) -> None:
    orphan_tmp = tmp_path / "experiment-orphan.parquet.tmp"
    _ = orphan_tmp.write_bytes(b"partial write from a crashed process")

    preview = invoke_cli(build_app(), ["cleanup-outputs", str(tmp_path)])
    assert preview.exit_code == 0, preview.output
    assert orphan_tmp.exists()  # preview keeps it

    executed = invoke_cli(build_app(), ["cleanup-outputs", str(tmp_path), "--execute"])
    assert executed.exit_code == 0, executed.output
    assert not orphan_tmp.exists()
