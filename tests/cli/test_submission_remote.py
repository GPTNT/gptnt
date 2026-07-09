"""Per-model discovery and copy seams that give `submission submit` one PR per model.

The GitHub-networked path (`create_submission`) is not exercised here; these cover the pure logic
that scopes a submission to a single model directory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from gptnt.cli.submission._remote import _copy_model, _model_dirs

if TYPE_CHECKING:
    from pathlib import Path


def _write_model(root: Path, model: str, *targets: str) -> Path:
    """Build submissions/<model>/<target>/{submission.yaml,experiments.parquet} under `root`."""
    model_dir = root / "submissions" / model
    for target in targets:
        target_dir = model_dir / target
        target_dir.mkdir(parents=True)
        _ = (target_dir / "submission.yaml").write_text(f"model: {model}\n")
        _ = (target_dir / "experiments.parquet").write_bytes(b"")
    return model_dir


def test_model_dirs_returns_one_entry_per_model(tmp_path: Path) -> None:
    _ = _write_model(tmp_path, "gpt-5-2_7bc641c3", "single-parametric-sync@1")
    _ = _write_model(tmp_path, "claude-sonnet-4-6_46a16b38", "multi-self-async@1")
    assert [path.name for path in _model_dirs(tmp_path)] == [
        "claude-sonnet-4-6_46a16b38",  # name-sorted
        "gpt-5-2_7bc641c3",
    ]


def test_model_dirs_errors_without_submissions_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="submissions/ directory"):
        _ = _model_dirs(tmp_path)


def test_model_dirs_errors_when_empty(tmp_path: Path) -> None:
    (tmp_path / "submissions").mkdir()
    with pytest.raises(ValueError, match="No model submission directories"):
        _ = _model_dirs(tmp_path)


def test_copy_model_scopes_to_one_model(tmp_path: Path) -> None:
    kept = _write_model(
        tmp_path, "gpt-5-2_7bc641c3", "single-parametric-sync@1", "multi-self-async@1"
    )
    _ = _write_model(tmp_path, "claude-sonnet-4-6_46a16b38", "multi-self-async@1")
    clone_dir = tmp_path / "clone"
    clone_dir.mkdir()

    rel_paths = _copy_model(kept, tmp_path, clone_dir)

    # Only the target model's files, anchored at submissions/<model>/...
    assert sorted(rel_paths) == [
        "submissions/gpt-5-2_7bc641c3/multi-self-async@1/experiments.parquet",
        "submissions/gpt-5-2_7bc641c3/multi-self-async@1/submission.yaml",
        "submissions/gpt-5-2_7bc641c3/single-parametric-sync@1/experiments.parquet",
        "submissions/gpt-5-2_7bc641c3/single-parametric-sync@1/submission.yaml",
    ]
    assert not any("claude-sonnet" in path for path in rel_paths)
    assert (clone_dir / "submissions/gpt-5-2_7bc641c3/multi-self-async@1/submission.yaml").exists()
    assert not (clone_dir / "submissions/claude-sonnet-4-6_46a16b38").exists()
