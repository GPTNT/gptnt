"""Behavioral tests for benchmark integrity and provenance capture."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

import pygit2
import pytest

from gptnt.provenance import (
    BenchmarkIntegrityError,
    Provenance,
    check_benchmark_integrity,
    gptnt_version,
)

if TYPE_CHECKING:
    from pathlib import Path

_RELEASE_TAG = "v0.15.0"

type ChangeKind = Literal[
    "modified", "deleted", "file_mode", "untracked", "replaced", "permitted", "unrelated"
]
type UnsupportedRepositoryState = Literal["no_repository", "no_release_tag"]


def _tagged_repository(tmp_path: Path) -> tuple[Path, str]:
    """Create a tagged repository containing each path-policy category."""
    repository = tmp_path / "repository"
    opened = pygit2.init_repository(repository)

    # Seed protected content, a permitted input, unrelated documentation, and an output ignore.
    files = {
        "src/gptnt/benchmark.py": "VALUE = 1\n",
        "configs/manual/sources.toml": "version = 1\n",
        "configs/player/custom.yaml": "model: example\n",
        "docs/notes.md": "notes\n",
        ".gitignore": "output/\n",
    }
    for relative_path, content in files.items():
        path = repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(content)

    index = opened.index
    index.add_all()
    index.write()
    signature = pygit2.Signature("Benchmark Test", "benchmark@example.com")
    release_commit = opened.create_commit(
        "HEAD", signature, signature, "release", index.write_tree(), []
    )
    # This commit and tag are the baseline for changes applied by each test.
    _ = opened.create_tag(
        _RELEASE_TAG,
        release_commit,
        pygit2.enums.ObjectType.COMMIT,
        signature,
        f"release {_RELEASE_TAG}",
    )
    # Integrity must detect executable-bit changes even when the checkout ignores them.
    opened.config["core.filemode"] = False
    return repository, str(release_commit)


def test_tagged_repository_supplies_integrity_and_provenance(tmp_path: Path) -> None:
    """Use the tagged baseline for both integrity reporting and provenance capture."""
    repository, release_commit = _tagged_repository(tmp_path)

    integrity = check_benchmark_integrity(repository)
    provenance = Provenance.capture(repository)

    assert (integrity.release_tag, integrity.release_commit) == (_RELEASE_TAG, release_commit)
    assert integrity.protected_content_modified is False
    assert provenance.model_dump() == {
        "gptnt_version": gptnt_version(),
        "release_commit": release_commit,
        "release_tag": _RELEASE_TAG,
        "protected_content_modified": False,
    }


def test_forced_capture_records_null_release_provenance(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)

    provenance = Provenance.capture(repository, force=True)

    assert provenance.model_dump() == {
        "gptnt_version": gptnt_version(),
        "release_commit": None,
        "release_tag": None,
        "protected_content_modified": None,
    }


def _apply_change(repository: Path, change: ChangeKind) -> None:
    """Apply one working-tree state from the path-policy table."""
    protected = repository / "src/gptnt/benchmark.py"
    match change:
        case "modified":
            _ = (repository / "configs/manual/sources.toml").write_text("version = 2\n")
        case "deleted":
            protected.unlink()
        case "file_mode":
            protected.chmod(protected.stat().st_mode | 0o111)
        case "untracked":
            _ = (repository / "src/gptnt/untracked.py").write_text("VALUE = 2\n")
        case "replaced":
            discovered = pygit2.discover_repository(str(repository))
            assert discovered is not None
            index = pygit2.Repository(discovered).index
            index.remove("src/gptnt/benchmark.py")
            index.write()
            _ = protected.write_text("VALUE = 2\n")
        case "permitted":
            _ = (repository / "configs/player/custom.yaml").write_text("model: changed\n")
        case "unrelated":
            _ = (repository / "docs/notes.md").write_text("changed\n")
            output = repository / "output/cache/data.bin"
            output.parent.mkdir(parents=True)
            _ = output.write_bytes(b"cache")


@pytest.mark.parametrize(
    ("change", "protected", "untracked", "permitted", "modified"),
    [
        # Tracked protected-content states.
        ("modified", ("configs/manual/sources.toml",), (), (), True),
        ("deleted", ("src/gptnt/benchmark.py",), (), (), True),
        ("file_mode", ("src/gptnt/benchmark.py",), (), (), True),
        # Cases with untracked paths or permitted input.
        ("untracked", (), ("src/gptnt/untracked.py",), (), True),
        ("replaced", ("src/gptnt/benchmark.py",), ("src/gptnt/benchmark.py",), (), True),
        ("permitted", (), (), ("configs/player/custom.yaml",), False),
        ("unrelated", (), (), (), False),
    ],
)
def test_path_policy(
    tmp_path: Path,
    change: ChangeKind,
    protected: tuple[str, ...],
    untracked: tuple[str, ...],
    permitted: tuple[str, ...],
    modified: bool,
) -> None:
    """Classify each Git state and derive modification from protected content."""
    repository, _ = _tagged_repository(tmp_path)
    _apply_change(repository, change)

    result = check_benchmark_integrity(repository)

    assert result.protected_changes == protected
    assert result.untracked_protected_files == untracked
    assert result.permitted_input_changes == permitted
    assert result.protected_content_modified is modified


@pytest.mark.parametrize(
    ("state", "condition"),
    [
        ("no_repository", "not a Git repository"),
        ("no_release_tag", "no exact annotated release tag"),
    ],
)
def test_unsupported_git_state_reports_repository_and_condition(
    tmp_path: Path, state: UnsupportedRepositoryState, condition: str
) -> None:
    """Report the repository path and unsupported Git condition in each error."""
    # Construct only the repository state needed to reach each error policy.
    match state:
        case "no_repository":
            repository = tmp_path
        case "no_release_tag":
            repository, _ = _tagged_repository(tmp_path)
            discovered = pygit2.discover_repository(str(repository))
            assert discovered is not None
            opened = pygit2.Repository(discovered)
            opened.references.delete(f"refs/tags/{_RELEASE_TAG}")
            signature = pygit2.Signature("Benchmark Test", "benchmark@example.com")
            _ = opened.create_tag(
                "v01.2.3",
                opened.head.target,
                pygit2.enums.ObjectType.COMMIT,
                signature,
                "not a SemVer release",
            )

    expected = rf"{re.escape(str(repository))}.*{condition}"
    with pytest.raises(BenchmarkIntegrityError, match=expected):
        _ = check_benchmark_integrity(repository)
