"""Compare a repository's protected content with its tagged release commit.

The input repository supplies the exact annotated release tag and tagged release commit used as the
protected-content baseline. The returned state separates protected changes from permitted input
changes. A missing repository or release tag, and multiple release tags on the same commit, prevent
the comparison.
"""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pygit2

if TYPE_CHECKING:
    from collections.abc import Iterator

PROTECTED_PATHS = (
    "src/gptnt",
    "pyproject.toml",
    "uv.lock",
    "mise.toml",
    "configs/player.yaml",
    "configs/anchors.yaml",
    "configs/hydra",
    "configs/manual",
    "configs/module_registry.yaml",
    "configs/suite_generator.yaml",
    "storage/prompts",
    "storage/manual",
    "storage/ktane/mods",
)
PERMITTED_INPUT_PATHS = ("configs/player", "configs/suites", "configs/missions", "runs")
RELEASE_TAG_PATTERN = r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"


class BenchmarkIntegrityError(RuntimeError):
    """The repository cannot supply a benchmark integrity result."""


@dataclass(frozen=True, kw_only=True)
class _BenchmarkIntegrityResult:
    release_tag: str
    release_commit: str
    protected_changes: tuple[str, ...]
    untracked_protected_files: tuple[str, ...]
    permitted_input_changes: tuple[str, ...]

    @property
    def protected_content_modified(self) -> bool:
        """Whether protected content differs from the release commit."""
        return bool(self.protected_changes or self.untracked_protected_files)


def _resolve_release_tag(
    repository: pygit2.Repository, *, release_commit: pygit2.Commit, worktree: Path
) -> str:
    release_tag_pattern = re.compile(RELEASE_TAG_PATTERN, re.ASCII)
    matching_references = []

    # Select annotated release tags that point directly to HEAD.
    for reference in repository.references.iterator(pygit2.enums.ReferenceFilter.TAGS):
        tag_name = reference.shorthand
        tag_object = repository[reference.target]

        if (
            release_tag_pattern.fullmatch(tag_name)
            and isinstance(tag_object, pygit2.Tag)
            and tag_object.target == release_commit.id
        ):
            matching_references.append(tag_name)

    # No tag and multiple tags are separate release-policy failures.
    if not matching_references:
        raise BenchmarkIntegrityError(
            f"Repository {worktree} HEAD has no exact annotated release tag matching "
            "vMAJOR.MINOR.PATCH"
        )
    if len(matching_references) > 1:
        formatted_references = ", ".join(sorted(matching_references))
        raise BenchmarkIntegrityError(
            f"Repository {worktree} HEAD has ambiguous annotated release tags: "
            f"{formatted_references}"
        )
    return matching_references[0]


def _paths_under_roots(paths: set[str], *, roots: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            path
            for path in paths
            if any(root == path or path.startswith(f"{root}/") for root in roots)
        )
    )


def _iter_release_files(
    tree: pygit2.Tree, *, prefix: str = ""
) -> Iterator[tuple[str, pygit2.Oid, pygit2.enums.FileMode]]:
    # Walk the release tree and retain each blob's content identity and file mode.
    for entry in tree:
        assert entry.name is not None
        path = f"{prefix}/{entry.name}" if prefix else entry.name

        if isinstance(entry, pygit2.Tree):
            yield from _iter_release_files(entry, prefix=path)
        elif isinstance(entry, pygit2.Blob):
            yield path, entry.id, entry.filemode


def _worktree_matches_release_file(
    path: Path, *, content_id: pygit2.Oid, file_mode: pygit2.enums.FileMode
) -> bool:
    # A missing path or a different filesystem object cannot match the release file.
    try:
        worktree_mode = path.lstat().st_mode
    except FileNotFoundError:
        return False

    # Git stores a symbolic link's target as its blob content.
    if file_mode == pygit2.enums.FileMode.LINK:
        return (
            stat.S_ISLNK(worktree_mode) and pygit2.hash(os.fsencode(path.readlink())) == content_id
        )

    # Regular files match on both content and executable state.
    return (
        stat.S_ISREG(worktree_mode)
        and pygit2.hashfile(str(path)) == content_id
        and (file_mode == pygit2.enums.FileMode.BLOB_EXECUTABLE) == bool(worktree_mode & 0o111)
    )


def _detect_tracked_worktree_changes(
    repository: pygit2.Repository, *, worktree: Path, release_tree: pygit2.Tree
) -> set[str]:
    # Compare content directly because index flags and cached stat data can suppress
    # status changes.
    release_files = {
        path: (content_id, file_mode)
        for path, content_id, file_mode in _iter_release_files(release_tree)
    }
    tracked_paths = set(release_files) | {entry.path for entry in repository.index}
    relevant_paths = _paths_under_roots(
        tracked_paths, roots=PROTECTED_PATHS + PERMITTED_INPUT_PATHS
    )
    changed_paths = set()

    for path in relevant_paths:
        release_file = release_files.get(path)
        if release_file is None or not _worktree_matches_release_file(
            worktree / path, content_id=release_file[0], file_mode=release_file[1]
        ):
            changed_paths.add(path)
    return changed_paths


def check_benchmark_integrity(repository: Path) -> _BenchmarkIntegrityResult:
    """Compare an input repository with the tagged baseline for its protected content.

    The repository's exact annotated release tag and release commit supply the baseline. The result
    reports tracked and untracked protected changes, permitted input changes, and whether protected
    content was modified. It raises
    `BenchmarkIntegrityError` when no repository is found or HEAD has no single exact annotated
    release tag. Other repository read failures propagate from their source.
    """
    # Resolve the working repository and its release baseline.
    discovered_repository = pygit2.discover_repository(str(repository))
    if discovered_repository is None:
        raise BenchmarkIntegrityError(f"Repository {repository} is not a Git repository")

    git_repository = pygit2.Repository(discovered_repository)
    worktree = Path(git_repository.workdir)
    release_commit = git_repository.head.peel(pygit2.Commit)
    release_tag = _resolve_release_tag(
        git_repository, release_commit=release_commit, worktree=worktree
    )

    # Separate untracked files while retaining combined index/worktree states in both sets.
    repository_status = git_repository.status(untracked_files="all", ignored=False)
    untracked_paths = {
        path for path, flags in repository_status.items() if flags & pygit2.enums.FileStatus.WT_NEW
    }
    tracked_change_paths = {
        path
        for path, flags in repository_status.items()
        if flags != pygit2.enums.FileStatus.WT_NEW
    }

    # The tagged-tree comparison detects content and mode changes hidden from repository status.
    tracked_change_paths.update(
        _detect_tracked_worktree_changes(
            git_repository, worktree=worktree, release_tree=release_commit.tree
        )
    )

    return _BenchmarkIntegrityResult(
        release_tag=release_tag,
        release_commit=str(release_commit.id),
        protected_changes=_paths_under_roots(tracked_change_paths, roots=PROTECTED_PATHS),
        untracked_protected_files=_paths_under_roots(untracked_paths, roots=PROTECTED_PATHS),
        permitted_input_changes=_paths_under_roots(
            tracked_change_paths | untracked_paths, roots=PERMITTED_INPUT_PATHS
        ),
    )
