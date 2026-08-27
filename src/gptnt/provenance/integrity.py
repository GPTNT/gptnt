"""Compare a repository's protected content with its tagged release commit.

The input repository supplies the annotated release history used to select a protected-content
baseline. The returned state separates protected changes from permitted input changes. A missing
repository or reachable semantic release tag prevents the comparison.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pygit2
from packaging.version import Version

from gptnt.provenance._protected_tree import (
    BenchmarkIntegrityError,
    _changed_protected_paths,
    _checkout_protected_tree,
    _git_protected_tree,
    _ProtectedTree,
)

# Submission schema 4 and its two provenance digest fields imply this v1 policy. Never mutate this
# root set or the v1 serializer: add a separately versioned policy and schema transition instead.
PROTECTED_PATHS_V1 = (
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
_DIGEST_POLICY_VERSION_V1 = 1


@dataclass(frozen=True, kw_only=True)
class _BenchmarkIntegrityResult:
    release_tag: str
    release_commit: str
    protected_changes: tuple[str, ...]
    permitted_input_changes: tuple[str, ...]
    release_protected_content_digest: str
    protected_content_digest: str

    @property
    def protected_content_modified(self) -> bool:
        """Whether protected content differs from the release commit."""
        return self.release_protected_content_digest != self.protected_content_digest


def _resolve_release(  # noqa: WPS231 - This filters tags before selecting the latest release.
    repository: pygit2.Repository, *, head: pygit2.Commit, worktree: Path
) -> tuple[str, pygit2.Commit]:
    release_tag_pattern = re.compile(RELEASE_TAG_PATTERN, re.ASCII)
    candidates: list[tuple[Version, str, pygit2.Commit]] = []

    for reference in repository.references.iterator(pygit2.enums.ReferenceFilter.TAGS):
        tag_name = reference.shorthand
        tag_object = repository[reference.target]
        if not release_tag_pattern.fullmatch(tag_name) or not isinstance(tag_object, pygit2.Tag):
            continue
        target = repository[tag_object.target]
        if not isinstance(target, pygit2.Commit):  # pyright: ignore[reportUnnecessaryIsInstance]
            continue
        if target.id == head.id or repository.descendant_of(head.id, target.id):
            candidates.append((Version(tag_name.removeprefix("v")), tag_name, target))

    if candidates:
        _, tag_name, commit = max(candidates, key=lambda candidate: candidate[0])
        return tag_name, commit
    raise BenchmarkIntegrityError(
        f"Repository {worktree} HEAD has no reachable annotated release tag matching "
        "vMAJOR.MINOR.PATCH"
    )


def _paths_under_roots(paths: set[str], *, roots: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            path
            for path in paths
            if any(root == path or path.startswith(f"{root}/") for root in roots)
        )
    )


@lru_cache(maxsize=4)
def _release_protected_tree(
    git_directory: str, release_commit: str, roots: tuple[str, ...], policy_version: int
) -> _ProtectedTree:
    if policy_version != _DIGEST_POLICY_VERSION_V1:
        raise BenchmarkIntegrityError(
            f"Unsupported protected-content digest policy version {policy_version}"
        )
    repository = pygit2.Repository(git_directory)
    commit = repository[pygit2.Oid(hex=release_commit)]
    if not isinstance(commit, pygit2.Commit):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise BenchmarkIntegrityError(f"Release object {release_commit} is not a commit")
    return _git_protected_tree(commit.tree, roots=roots)


def release_protected_content_digest(  # noqa: WPS238 - Identity violations need distinct messages.
    repository: Path, *, release_tag: str, release_commit: str
) -> str:
    """Recompute protected content for one exact annotated release identity."""
    if re.fullmatch(RELEASE_TAG_PATTERN, release_tag, flags=re.ASCII) is None:
        raise BenchmarkIntegrityError(
            f"Release tag {release_tag!r} is not an exact semantic release tag"
        )
    discovered_repository = pygit2.discover_repository(str(repository))
    if discovered_repository is None:
        raise BenchmarkIntegrityError(f"Repository {repository} is not a Git repository")
    git_repository = pygit2.Repository(discovered_repository)
    reference_name = f"refs/tags/{release_tag}"
    try:
        reference = git_repository.references[reference_name]
    except KeyError as error:
        raise BenchmarkIntegrityError(f"Release tag {release_tag!r} does not exist") from error
    tag_object = git_repository[reference.target]
    if not isinstance(tag_object, pygit2.Tag):
        raise BenchmarkIntegrityError(f"Release tag {release_tag!r} is not annotated")
    target = git_repository[tag_object.target]
    if not isinstance(target, pygit2.Commit):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise BenchmarkIntegrityError(f"Release tag {release_tag!r} does not target a commit")
    if str(target.id) != release_commit:
        raise BenchmarkIntegrityError(
            f"Release tag {release_tag!r} does not target recorded commit {release_commit}"
        )
    return _release_protected_tree(
        str(discovered_repository), release_commit, PROTECTED_PATHS_V1, _DIGEST_POLICY_VERSION_V1
    ).digest


def check_benchmark_integrity(repository: Path) -> _BenchmarkIntegrityResult:
    """Compare an input repository with the tagged baseline for its protected content.

    The repository's exact annotated release tag and release commit supply the baseline. The result
    reports canonical protected-tree differences, permitted input changes, and whether protected
    content was modified. It raises `BenchmarkIntegrityError` when no repository is found or HEAD
    has no reachable annotated semantic release tag. Other repository read failures propagate from
    their source.
    """
    # Resolve the working repository and its release baseline.
    discovered_repository = pygit2.discover_repository(str(repository))
    if discovered_repository is None:
        raise BenchmarkIntegrityError(f"Repository {repository} is not a Git repository")

    git_repository = pygit2.Repository(discovered_repository)
    worktree = Path(git_repository.workdir)
    head = git_repository.head.peel(pygit2.Commit)
    release_tag, release_commit = _resolve_release(git_repository, head=head, worktree=worktree)

    release_tree = _release_protected_tree(
        str(discovered_repository),
        str(release_commit.id),
        PROTECTED_PATHS_V1,
        _DIGEST_POLICY_VERSION_V1,
    )
    checkout_tree = _checkout_protected_tree(worktree, roots=PROTECTED_PATHS_V1)

    # Git status remains relevant only for user-controlled input paths.
    repository_status = git_repository.status(untracked_files="all", ignored=False)
    changed_paths = set(repository_status)

    return _BenchmarkIntegrityResult(
        release_tag=release_tag,
        release_commit=str(release_commit.id),
        protected_changes=_changed_protected_paths(release_tree, checkout_tree),
        permitted_input_changes=_paths_under_roots(changed_paths, roots=PERMITTED_INPUT_PATHS),
        release_protected_content_digest=release_tree.digest,
        protected_content_digest=checkout_tree.digest,
    )
