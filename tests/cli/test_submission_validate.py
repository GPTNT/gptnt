"""Tests for `gptnt submission validate`, driven off a real bundle built by the real writers.

A fully covering interactive bundle for the solo leaderboard suite is built once (one solved run
per mission in the suite's set), then each test copies and breaks exactly one thing. Success paths
go through the CLI; failure paths call the command directly and assert the raised `RuntimeError`
(per `tests/_cli_runner.py`).
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING, Any

import pytest
import yaml
from pydantic_ai import RunUsage

from gptnt.cli.__main__ import build_app
from gptnt.cli.submission._bundle import InteractiveBundle, StaticsBundle, load_submission_bundle
from gptnt.cli.submission._schema import SubmissionExperiment
from gptnt.cli.submission.validate import validate_submission
from gptnt.common.paths import Paths
from gptnt.experiments.db.typed_parquet import read_typed_parquet, write_typed_parquet
from gptnt.experiments.generation.missions import load_missions
from gptnt.experiments.generation.pipeline import compose_suite
from gptnt.experiments.models import ExperimentSummary

from tests._cli_runner import invoke_cli
from tests._factories.experiments import (
    make_experiment_descriptor,
    make_experiment_spec,
    make_solved_bomb,
)
from tests._factories.statics import write_statics_run

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.experiments.suite import Suite
    from gptnt.ktane.mission_spec import KtaneMissionSpec

SUITE = "single-parametric-sync"


def _make_experiment(mission: KtaneMissionSpec, suite: Suite) -> SubmissionExperiment:
    """One valid, solved run of `mission` recorded against `suite`."""
    spec = make_experiment_spec(seed=mission.seed).model_copy(
        update={
            "mission_spec": mission,
            "mission_set": suite.mission_set,
            "suite_name": suite.name,
            "suite_revision": suite.revision,
        }
    )
    summary = ExperimentSummary.from_descriptor_and_bomb_state(
        descriptor=make_experiment_descriptor(spec),
        final_bomb_state=make_solved_bomb(),
        is_hard_crash=False,
        gptnt_version="0.15.0",
        git_sha="a1b2c3d4",
    )
    return SubmissionExperiment.from_summary(
        summary=summary, final_bomb_state=make_solved_bomb(), usage_by_role={"defuser": RunUsage()}
    )


def _read_manifest(bundle_dir: Path) -> dict[str, Any]:
    return yaml.safe_load((bundle_dir / "submission.yaml").read_text())


def _write_manifest(bundle_dir: Path, manifest: dict[str, Any]) -> None:
    _ = (bundle_dir / "submission.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))


def _fill_submitter(bundle_dir: Path) -> None:
    manifest = _read_manifest(bundle_dir)
    manifest["submitter"] = {"name": "Ada Lovelace", "contact": "@ada", "affiliation": None}
    _write_manifest(bundle_dir, manifest)


@pytest.fixture(scope="module")
def suite() -> Suite:
    return compose_suite(SUITE)


@pytest.fixture(scope="module")
def valid_bundle_root(tmp_path_factory: pytest.TempPathFactory, suite: Suite) -> Path:
    """A submissions root holding one fully covering, submitter-filled interactive bundle."""
    root = tmp_path_factory.mktemp("submissions")
    missions = load_missions(Paths().root / suite.missions_path)
    experiments = [_make_experiment(mission, suite) for mission in missions]
    _fill_submitter(InteractiveBundle.from_experiments(experiments, suite).save(root))
    return root


@pytest.fixture
def bundle_copy(valid_bundle_root: Path, tmp_path: Path) -> Path:
    """A fresh mutable copy of the valid bundle tree; returns the bundle dir itself."""
    root = tmp_path / "submissions"
    shutil.copytree(valid_bundle_root, root)
    return next(root.rglob("submission.yaml")).parent


def _assert_validate_fails(path: Path) -> None:
    with pytest.raises(RuntimeError, match="Validation found problems"):
        validate_submission(path)


def _unwrap_output(capsys: pytest.CaptureFixture[str]) -> str:
    """The output whitespace-collapsed; assert on `✗ <check-name>` (that column never wraps)."""
    return " ".join(capsys.readouterr().out.split())


def test_bundle_round_trips_through_save_and_load(bundle_copy: Path) -> None:
    loaded = load_submission_bundle(bundle_copy)
    assert isinstance(loaded, InteractiveBundle)
    assert loaded.manifest.target == bundle_copy.name
    assert len(loaded.experiments) == len(
        read_typed_parquet(SubmissionExperiment, bundle_copy / "experiments.parquet")
    )
    # Saving what was loaded reproduces the same directory (submitter edits survive the merge).
    assert loaded.save(bundle_copy.parent.parent) == bundle_copy
    assert _read_manifest(bundle_copy)["submitter"]["name"] == "Ada Lovelace"


def test_valid_bundle_passes(bundle_copy: Path) -> None:
    result = invoke_cli(build_app(), ["submission", "validate", str(bundle_copy)])
    assert result.exit_code == 0, result.output
    assert "✗" not in result.output
    assert "1 ok, 0 failed" in result.output


def test_missing_mission_fails(bundle_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    experiments = read_typed_parquet(SubmissionExperiment, bundle_copy / "experiments.parquet")
    write_typed_parquet(experiments[1:], file_path=bundle_copy / "experiments.parquet")

    _assert_validate_fails(bundle_copy)
    assert "✗ missing" in _unwrap_output(capsys)


def test_duplicate_mission_fails(bundle_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    experiments = read_typed_parquet(SubmissionExperiment, bundle_copy / "experiments.parquet")
    write_typed_parquet(
        [*experiments, experiments[0]], file_path=bundle_copy / "experiments.parquet"
    )

    _assert_validate_fails(bundle_copy)
    assert "✗ duplicates" in _unwrap_output(capsys)


def test_unknown_mission_fails(bundle_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    experiments = read_typed_parquet(SubmissionExperiment, bundle_copy / "experiments.parquet")
    foreign = experiments[0].model_copy(update={"seed": 999_999_999})
    write_typed_parquet([*experiments[1:], foreign], file_path=bundle_copy / "experiments.parquet")

    _assert_validate_fails(bundle_copy)
    assert "✗ unknown" in _unwrap_output(capsys)


def test_invalid_run_fails(bundle_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    experiments = read_typed_parquet(SubmissionExperiment, bundle_copy / "experiments.parquet")
    crashed = experiments[0].model_copy(update={"is_hard_crash": True})
    write_typed_parquet([crashed, *experiments[1:]], file_path=bundle_copy / "experiments.parquet")

    _assert_validate_fails(bundle_copy)
    assert "✗ outcomes" in _unwrap_output(capsys)


def test_blank_submitter_fails(bundle_copy: Path) -> None:
    manifest = _read_manifest(bundle_copy)
    manifest["submitter"] = {"name": "", "contact": "", "affiliation": None}
    _write_manifest(bundle_copy, manifest)

    _assert_validate_fails(bundle_copy)


def test_tampered_suite_digest_fails(bundle_copy: Path) -> None:
    manifest = _read_manifest(bundle_copy)
    manifest["measured"]["suite_digest"] = "deadbeef"
    _write_manifest(bundle_copy, manifest)

    _assert_validate_fails(bundle_copy)


def test_tampered_written_fingerprint_fails(bundle_copy: Path) -> None:
    manifest = _read_manifest(bundle_copy)
    manifest["players"][0]["fingerprint"] = "deadbeef"
    _write_manifest(bundle_copy, manifest)

    _assert_validate_fails(bundle_copy)


def test_renamed_model_dir_fails(bundle_copy: Path) -> None:
    model_dir = bundle_copy.parent
    renamed = model_dir.with_name("test-defuser_00000000")
    model_dir.rename(renamed)

    _assert_validate_fails(renamed / bundle_copy.name)


def test_missing_payload_fails(bundle_copy: Path) -> None:
    (bundle_copy / "experiments.parquet").unlink()

    _assert_validate_fails(bundle_copy)


def test_dirty_git_sha_warns_but_passes(bundle_copy: Path) -> None:
    manifest = _read_manifest(bundle_copy)
    manifest["provenance"]["git_sha"] = "a1b2c3d4-dirty"
    _write_manifest(bundle_copy, manifest)

    result = invoke_cli(build_app(), ["submission", "validate", str(bundle_copy)])
    assert result.exit_code == 0, result.output
    assert "⚠" in result.output


def test_sweep_reports_every_bundle(bundle_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A root with one good and one broken bundle fails overall but renders both."""
    root = bundle_copy.parent.parent
    broken = root / "broken" / bundle_copy.name
    shutil.copytree(bundle_copy, broken)  # the copy's dir no longer matches its manifest

    _assert_validate_fails(root)
    assert "1 ok, 1 failed" in _unwrap_output(capsys)


def _build_statics_bundle(
    tmp_path: Path,
    *,
    requested_revision: str | None = "v1",
    resolved_revision: str | None = "a1b2c3d4e5f6",
) -> Path:
    run_dir = write_statics_run(
        tmp_path / "statics",
        requested_revision=requested_revision,
        resolved_revision=resolved_revision,
    )
    bundle_dir = StaticsBundle.from_run_dir(run_dir).save(tmp_path / "submissions")
    _fill_submitter(bundle_dir)
    return bundle_dir


def test_valid_statics_bundle_passes(tmp_path: Path) -> None:
    bundle_dir = _build_statics_bundle(tmp_path)

    result = invoke_cli(build_app(), ["submission", "validate", str(bundle_dir)])
    assert result.exit_code == 0, result.output
    assert "✗" not in result.output


def test_unpinned_statics_dataset_warns_but_passes(tmp_path: Path) -> None:
    bundle_dir = _build_statics_bundle(tmp_path, requested_revision=None, resolved_revision=None)

    result = invoke_cli(build_app(), ["submission", "validate", str(bundle_dir)])
    assert result.exit_code == 0, result.output
    assert "⚠" in result.output


def test_corrupt_statics_metrics_fails(tmp_path: Path) -> None:
    bundle_dir = _build_statics_bundle(tmp_path)
    _ = (bundle_dir / "metrics.json").write_text("{not json")

    _assert_validate_fails(bundle_dir)


def test_empty_root_errors(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="No bundles under"):
        validate_submission(tmp_path)
