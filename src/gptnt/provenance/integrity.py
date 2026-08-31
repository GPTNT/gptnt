"""Compare checkout content with the latest annotated release reachable from `HEAD`.

Protected paths are compared as canonical trees. Git status is used only to report changes below
the permitted input roots. A repository without a reachable semantic release tag cannot be checked.
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
    _ProtectedTree,
    build_checkout_protected_tree,
    build_git_protected_tree,
    find_changed_protected_paths,
)

# Submission schema 4 and its two provenance digest fields imply this v1 policy. Never mutate this
# root set or the v1 serializer: add a separately versioned policy and schema transition instead.
PROTECTED_PATHS_V1 = (
    ".gitattributes",
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
    """Selected release, tree identities, and changed paths for one checkout."""

    release_tag: str
    """Annotated semantic-version tag selected as the release baseline."""

    release_commit: str
    """Commit targeted by the selected release tag."""

    changed_protected_paths: tuple[str, ...]
    """Protected paths whose release and checkout entries differ."""

    changed_input_paths: tuple[str, ...]
    """Changed paths below the permitted input roots."""

    release_digest: str
    """Protected-tree digest calculated from the release commit."""

    checkout_digest: str
    """Protected-tree digest calculated from the checkout."""

    @property
    def protected_content_modified(self) -> bool:
        """Whether protected content differs from the release commit."""
        return self.release_digest != self.checkout_digest


@dataclass(frozen=True, kw_only=True)
class _ReleaseBaseline:
    """Annotated release tag and commit selected as the comparison baseline."""

    tag: str
    """Selected annotated semantic-version tag."""

    commit: pygit2.Commit
    """Commit targeted by the selected tag."""


def _select_release_baseline(  # noqa: WPS231 - This filters the Git tags before selecting the latest release.
    repository: pygit2.Repository, *, head: pygit2.Commit, worktree: Path
) -> _ReleaseBaseline:
    """Select the highest semantic annotated release reachable from `head`."""
    release_tag_pattern = re.compile(RELEASE_TAG_PATTERN, re.ASCII)
    reachable_releases: list[tuple[Version, _ReleaseBaseline]] = []

    for reference in repository.references.iterator(pygit2.enums.ReferenceFilter.TAGS):
        tag_name = reference.shorthand
        tag_object = repository[reference.target]
        if not release_tag_pattern.fullmatch(tag_name) or not isinstance(tag_object, pygit2.Tag):
            continue
        target = repository[tag_object.target]
        if not isinstance(target, pygit2.Commit):  # pyright: ignore[reportUnnecessaryIsInstance]
            continue
        if target.id == head.id or repository.descendant_of(head.id, target.id):
            reachable_releases.append(
                (
                    Version(tag_name.removeprefix("v")),
                    _ReleaseBaseline(tag=tag_name, commit=target),
                )
            )

    if reachable_releases:
        # Each item is `(semantic version, baseline)`: select by version, then return the baseline.
        return max(reachable_releases, key=lambda release: release[0])[1]
    raise BenchmarkIntegrityError(
        f"Repository {worktree} HEAD has no reachable annotated release tag matching "
        "vMAJOR.MINOR.PATCH"
    )


def _changed_paths_within(paths: set[str], *, roots: tuple[str, ...]) -> tuple[str, ...]:
    """Return changed paths at or below the requested roots."""
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
    """Return the cached v1 protected tree for an exact release commit."""
    if policy_version != _DIGEST_POLICY_VERSION_V1:
        raise BenchmarkIntegrityError(
            f"Unsupported protected-content digest policy version {policy_version}"
        )
    repository = pygit2.Repository(git_directory)
    commit = repository[pygit2.Oid(hex=release_commit)]
    if not isinstance(commit, pygit2.Commit):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise BenchmarkIntegrityError(f"Release object {release_commit} is not a commit")
    return build_git_protected_tree(commit.tree, roots=roots)


def compute_release_protected_content_digest(  # noqa: WPS238 - Identity violations need distinct messages.
    repository: Path, *, release_tag: str, release_commit: str
) -> str:
    """Return the v1 protected-tree digest for an exact annotated release."""
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
    """Compare protected checkout content with its reachable release baseline.

    Select the highest semantic annotated release reachable from `HEAD`. Build the v1 protected
    tree from that commit and from the checkout, then report their identities and changed paths.
    Raise `BenchmarkIntegrityError` when the repository or release baseline is unavailable.
    """
    # Locate the checkout and select the release commit used for the protected-tree comparison.
    discovered_repository = pygit2.discover_repository(str(repository))
    if discovered_repository is None:
        raise BenchmarkIntegrityError(f"Repository {repository} is not a Git repository")

    git_repository = pygit2.Repository(discovered_repository)
    worktree = Path(git_repository.workdir)
    head = git_repository.head.peel(pygit2.Commit)
    baseline = _select_release_baseline(git_repository, head=head, worktree=worktree)

    # The release tree is immutable and cached. The checkout tree is rebuilt on every call so local
    # changes cannot be hidden by the cache.
    release_tree = _release_protected_tree(
        str(discovered_repository),
        str(baseline.commit.id),
        PROTECTED_PATHS_V1,
        _DIGEST_POLICY_VERSION_V1,
    )
    checkout_tree = build_checkout_protected_tree(worktree, roots=PROTECTED_PATHS_V1)

    # Git status remains relevant only for user-controlled input paths.
    repository_status = git_repository.status(untracked_files="all", ignored=False)
    changed_paths = set(repository_status)

    return _BenchmarkIntegrityResult(
        release_tag=baseline.tag,
        release_commit=str(baseline.commit.id),
        changed_protected_paths=find_changed_protected_paths(release_tree, checkout_tree),
        changed_input_paths=_changed_paths_within(changed_paths, roots=PERMITTED_INPUT_PATHS),
        release_digest=release_tree.digest,
        checkout_digest=checkout_tree.digest,
    )
