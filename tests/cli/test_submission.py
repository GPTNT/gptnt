"""End-to-end tests for `gptnt submission new` / `validate`, built from real records and outputs.

Success and parse paths go through `invoke_cli`; a check's *failure* is asserted by calling
`validate_submission` directly with `pytest.raises`, since cyclopts turns a raise into an exit.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from gptnt.cli.__main__ import build_app
from gptnt.cli.submission._io import read_experiments, read_yaml, write_experiments, write_yaml
from gptnt.cli.submission._statics import build_statics_submission
from gptnt.cli.submission.validate import validate_submission
from gptnt.experiments.recorder.parquet import (
    RecordFooter,
    build_footer,
    write_player_record_parquet,
)
from gptnt.ktane.state.bomb import BombState
from gptnt.specification import PlayerCapabilities

from tests._cli_runner import invoke_cli
from tests._factories.experiments import make_experiment_descriptor, make_experiment_spec

if TYPE_CHECKING:
    from pathlib import Path

CLEAN_SHA = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"


def _bomb() -> BombState:
    """A solved bomb (empty modules; the is-solved validator marks an empty bomb solved)."""
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
                "secondsRemaining": 100.0,
            },
            "widgets": [],
            "modules": [],
        }
    )


def _write_record(outputs: Path, *, seed: int, git_sha: str = CLEAN_SHA) -> None:
    """Write one completed defuser record with a controllable git_sha in its footer."""
    descriptor = make_experiment_descriptor(make_experiment_spec(seed=seed))
    footer = RecordFooter(
        descriptor=descriptor,
        final_bomb_state=_bomb(),
        is_hard_crash=False,
        role="defuser",
        gptnt_version="0.15.0",
        git_sha=git_sha,
    )
    write_player_record_parquet(
        blobbed_steps=[],
        footer=build_footer(footer, player_uuid=str(uuid4())),
        output_path=outputs / f"experiment-{uuid4()}.parquet",
    )


@pytest.fixture
def outputs_dir(tmp_path: Path) -> Path:
    """A recorder outputs dir with three completed experiments, all cleanly committed."""
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    for seed in (1, 2, 3):
        _write_record(outputs, seed=seed)
    return outputs


def _build_bundle(outputs: Path, into: Path) -> Path:
    """Build the interactive bundle via the CLI and return its directory."""
    result = invoke_cli(build_app(), ["submission", "new", str(outputs), "--into", str(into)])
    assert result.exit_code == 0, result.output
    bundle_dir = next(into.rglob("submission.yaml")).parent
    return bundle_dir


def test_new_writes_a_bundle(outputs_dir: Path, tmp_path: Path) -> None:
    bundle_dir = _build_bundle(outputs_dir, tmp_path / "submissions")

    assert (bundle_dir / "submission.yaml").exists()
    assert len(read_experiments(bundle_dir / "experiments.parquet")) == 3
    manifest = read_yaml(bundle_dir / "submission.yaml")
    assert manifest["system"]["model"] == "test-defuser"
    assert manifest["suite"]["suite_name"] == "single-parametric-sync"


def test_validate_passes_on_a_clean_bundle(outputs_dir: Path, tmp_path: Path) -> None:
    bundle_dir = _build_bundle(outputs_dir, tmp_path / "submissions")

    result = invoke_cli(build_app(), ["submission", "validate", str(bundle_dir)])

    assert result.exit_code == 0, result.output


def test_validate_fails_on_a_tampered_stat(outputs_dir: Path, tmp_path: Path) -> None:
    bundle_dir = _build_bundle(outputs_dir, tmp_path / "submissions")
    manifest = read_yaml(bundle_dir / "submission.yaml")
    manifest["stats"]["headline"]["solve_rate"] = 0.123
    write_yaml(bundle_dir / "submission.yaml", manifest)

    with pytest.raises(RuntimeError, match="validation failed"):
        validate_submission(bundle_dir)


def test_validate_fails_on_an_altered_outcome(outputs_dir: Path, tmp_path: Path) -> None:
    bundle_dir = _build_bundle(outputs_dir, tmp_path / "submissions")
    experiments = read_experiments(bundle_dir / "experiments.parquet")
    # Flip an outcome flag away from what its (untouched) final bomb state derives.
    experiments[0] = experiments[0].model_copy(update={"is_solved": False, "is_detonated": True})
    write_experiments(bundle_dir / "experiments.parquet", experiments)

    with pytest.raises(RuntimeError, match="validation failed"):
        validate_submission(bundle_dir)


def test_validate_fails_on_an_edited_suite_digest(outputs_dir: Path, tmp_path: Path) -> None:
    bundle_dir = _build_bundle(outputs_dir, tmp_path / "submissions")
    manifest = read_yaml(bundle_dir / "submission.yaml")
    manifest["suite"]["suite_digest"] = "deadbeef"
    write_yaml(bundle_dir / "submission.yaml", manifest)

    with pytest.raises(RuntimeError, match="validation failed"):
        validate_submission(bundle_dir)


def test_validate_fails_on_an_edited_fingerprint(outputs_dir: Path, tmp_path: Path) -> None:
    bundle_dir = _build_bundle(outputs_dir, tmp_path / "submissions")
    manifest = read_yaml(bundle_dir / "submission.yaml")
    manifest["capabilities"]["defuser"]["fingerprint"] = "0" * 32
    write_yaml(bundle_dir / "submission.yaml", manifest)

    with pytest.raises(RuntimeError, match="validation failed"):
        validate_submission(bundle_dir)


def test_validate_fails_on_a_dirty_sha(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    _write_record(outputs, seed=1, git_sha=f"{CLEAN_SHA}-dirty")
    bundle_dir = _build_bundle(outputs, tmp_path / "submissions")

    with pytest.raises(RuntimeError, match="validation failed"):
        validate_submission(bundle_dir)


def _write_statics_outputs(root: Path) -> Path:
    """A statics outputs dir with predictions, metrics, and a stamped run_meta.json."""
    out = root / "expert-ocr_predictions" / "gpt-5.2"
    out.mkdir(parents=True)
    capabilities = PlayerCapabilities(player_name="gpt-5.2", player_type="ai")
    _ = (out / "run_meta.json").write_text(
        json.dumps(
            {
                "task_name": "expert-ocr",
                "model_name": "gpt-5.2",
                "run_date": "2026-07-02T10:00:00Z",
                "dataset": {
                    "hf_repo_id": "GPTNT/expert-element-ocr",
                    "dataset_split": None,
                    "requested_revision": "v1",
                    "resolved_revision": CLEAN_SHA,
                },
                "capabilities": capabilities.model_dump(mode="json"),
                "provenance": {"gptnt_version": "0.15.0", "git_sha": CLEAN_SHA},
            }
        )
    )
    _ = (out / "metrics.json").write_text(json.dumps({"module": {"total": 0.87}}))
    for index in range(3):
        _ = (out / f"prediction_{index}.json").write_text(
            json.dumps(
                {
                    "index": index,
                    "usage": {"input_tokens": 10},
                    "model": "gpt-5.2",
                    "output": f"answer-{index}",
                    "thoughts": None,
                    "raw_output": None,
                    "error": None,
                    "exception": None,
                }
            )
        )
    return out


def test_statics_new_and_validate(tmp_path: Path) -> None:
    outputs = _write_statics_outputs(tmp_path)

    bundle_dir = build_statics_submission(outputs, "expert-ocr", tmp_path / "submissions")

    assert (bundle_dir / "predictions.parquet").exists()
    assert (bundle_dir / "metrics.json").exists()
    result = invoke_cli(build_app(), ["submission", "validate", str(bundle_dir)])
    assert result.exit_code == 0, result.output


def test_statics_validate_fails_on_model_mismatch(tmp_path: Path) -> None:
    outputs = _write_statics_outputs(tmp_path)
    bundle_dir = build_statics_submission(outputs, "expert-ocr", tmp_path / "submissions")
    manifest = read_yaml(bundle_dir / "submission.yaml")
    manifest["system"]["model"] = "not-the-model"
    write_yaml(bundle_dir / "submission.yaml", manifest)

    with pytest.raises(RuntimeError, match="validation failed"):
        validate_submission(bundle_dir)


def test_statics_revision_flag_is_wired() -> None:
    result = invoke_cli(build_app(), ["statics", "expert-ocr", "--help"])

    assert "--dataset-revision" in result.output
