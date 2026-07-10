"""Per-bundle discovery, copy, and dry-run submit seams that give `submit` one PR per model.

The GitHub-networked path is not exercised. `_submit_one_bundle` is driven on its dry-run branch
against a real local pygit2 repo, which never touches `source_repo`, so no GitHub object is faked.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

# The GitHub/git path lives behind the opt-in `submission` extra; skip the whole module when it is
# not installed rather than failing collection (`_remote` imports both at runtime too).
pytest.importorskip("pygit2")
pytest.importorskip("github")

import pygit2

from gptnt.cli.submission._remote import DRY_RUN_PR_URL, _SubmissionSession, _submit_one_bundle
from gptnt.cli.submission._staging import all_bundle_dirs, copy_bundle

if TYPE_CHECKING:
    from pathlib import Path

    from github.Repository import Repository as GhRepository


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
    assert [path.name for path in all_bundle_dirs(tmp_path)] == [
        "claude-sonnet-4-6_46a16b38",  # name-sorted
        "gpt-5-2_7bc641c3",
    ]


def test_model_dirs_errors_without_submissions_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="submissions/ directory"):
        _ = all_bundle_dirs(tmp_path)


def test_model_dirs_errors_when_empty(tmp_path: Path) -> None:
    (tmp_path / "submissions").mkdir()
    with pytest.raises(FileNotFoundError, match="No bundle submission directories"):
        _ = all_bundle_dirs(tmp_path)


def test_copy_model_scopes_to_one_model(tmp_path: Path) -> None:
    kept = _write_model(
        tmp_path, "gpt-5-2_7bc641c3", "single-parametric-sync@1", "multi-self-async@1"
    )
    _ = _write_model(tmp_path, "claude-sonnet-4-6_46a16b38", "multi-self-async@1")
    clone_dir = tmp_path / "clone"
    clone_dir.mkdir()

    rel_paths = copy_bundle(kept, tmp_path, clone_dir)

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


def _dry_run_session(
    *, repo: pygit2.Repository, submission_dir: Path, clone_dir: Path, signature: pygit2.Signature
) -> _SubmissionSession:
    return _SubmissionSession(
        repo=repo,
        # The dry-run path never dereferences source_repo; a bare object proves it stays untouched.
        source_repo=cast("GhRepository", object()),
        default_branch="main",
        login="octocat",
        token="",  # only used on the real push path
        can_push=True,
        base_commit=repo.head.peel(pygit2.Commit),
        signature=signature,
        submission_dir=submission_dir,
        clone_dir=clone_dir,
        slug="gptnt/submissions",
        body="",
        dry_run=True,
    )


def test_submit_one_bundle_dry_run_commits_only_that_bundle(tmp_path: Path) -> None:
    clone_dir = tmp_path / "clone"
    repo = pygit2.init_repository(str(clone_dir), initial_head="main")
    signature = pygit2.Signature("Test", "test@example.com")
    base_oid = repo.create_commit(
        "HEAD", signature, signature, "init", repo.index.write_tree(), []
    )

    kept = _write_model(tmp_path, "gpt-5-2_7bc641c3", "single-parametric-sync@1")
    _ = _write_model(tmp_path, "claude-sonnet-4-6_46a16b38", "multi-self-async@1")

    result = _submit_one_bundle(
        _dry_run_session(
            repo=repo, submission_dir=tmp_path, clone_dir=clone_dir, signature=signature
        ),
        kept,
    )

    assert result.bundle == "gpt-5-2_7bc641c3"
    assert result.branch == "octocat/add-gpt-5-2_7bc641c3"
    assert result.pr_url == DRY_RUN_PR_URL
    assert result.error is None

    # A real commit landed on the bundle's branch, off base, carrying only that bundle's files.
    committed = repo.diff(
        repo[base_oid].peel(pygit2.Commit),
        repo.branches.local["octocat/add-gpt-5-2_7bc641c3"].peel(pygit2.Commit),
    )
    assert sorted(delta.new_file.path for delta in committed.deltas) == [
        "submissions/gpt-5-2_7bc641c3/single-parametric-sync@1/experiments.parquet",
        "submissions/gpt-5-2_7bc641c3/single-parametric-sync@1/submission.yaml",
    ]
