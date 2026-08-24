from __future__ import annotations

from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Self

import pygit2
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, Field, field_validator, model_validator

from gptnt.provenance.integrity import RELEASE_TAG_PATTERN, check_benchmark_integrity

# Used when the package metadata or git state can't be resolved (e.g. an exotic install layout).
UNKNOWN_VERSION = "0.0.0"
_MODULE_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def gptnt_version() -> str:
    """Resolved gptnt version, e.g. `0.13.2` or `0.13.2.dev3+g<sha>` between releases."""
    try:
        return version("gptnt")
    except PackageNotFoundError:
        return UNKNOWN_VERSION


@lru_cache(maxsize=1)
def git_sha() -> str | None:
    """Current commit for the checkout containing the installed package, if available."""
    try:  # noqa: WPS229 - Treat the complete optional checkout read as unavailable on failure.
        repository_path = pygit2.discover_repository(str(_MODULE_DIR))
        if repository_path is None:
            return None
        repository = pygit2.Repository(repository_path)
        return str(repository.head.peel(pygit2.Commit).id)
    except (OSError, pygit2.GitError):
        return None


def is_valid_version(recorded: str | None) -> bool:
    """Return whether a recorded version is resolvable.

    A valid version must parse as a version (PEP 440/SemVer) AND not be the `UNKNOWN_VERSION`
    fallback we stamp when the package metadata can't be resolved.
    """
    if recorded is None or not recorded.strip() or recorded.strip() == UNKNOWN_VERSION:
        return False
    try:
        _ = Version(recorded)
    except InvalidVersion:
        return False
    return True


class Provenance(BaseModel):
    """Release provenance captured when a record is created.

    `capture` reads the release tag and release commit from the checkout at that point. Stored
    records must supply every field and are never completed from the checkout that later reads
    them.
    """

    gptnt_version: str
    """Installed GPTNT package version that created the record."""

    release_commit: str | None = Field(min_length=1)
    """Release commit recorded for the benchmark run, if integrity was established."""

    release_tag: str | None = Field(pattern=rf"^{RELEASE_TAG_PATTERN}$")
    """Exact release tag identifying the protected-content baseline, if established."""

    protected_content_modified: bool | None
    """Whether protected content differed from the tagged baseline, if one was established."""

    @classmethod
    def capture(cls, repository: Path = _MODULE_DIR, *, force: bool = False) -> Provenance:
        """Capture release provenance, or record its absence for a forced execution."""
        if force:
            return cls(
                gptnt_version=gptnt_version(),
                release_commit=None,
                release_tag=None,
                protected_content_modified=None,
            )
        integrity = check_benchmark_integrity(repository)
        return cls(
            gptnt_version=gptnt_version(),
            release_commit=integrity.release_commit,
            release_tag=integrity.release_tag,
            protected_content_modified=integrity.protected_content_modified,
        )

    @field_validator("gptnt_version")
    @classmethod
    def _reject_unknown_version(cls, recorded: str) -> str:
        """Reject a blank, invalid, or unresolved recorded version."""
        if not is_valid_version(recorded):
            raise ValueError(
                f"gptnt_version {recorded!r} is not a valid version "
                "(must be a semantic version, not blank or the unknown marker)"
            )
        return recorded

    @field_validator("release_commit")
    @classmethod
    def _reject_dirty_release_commit(cls, recorded: str | None) -> str | None:
        if recorded is None:
            return None
        if recorded.endswith("-dirty"):
            raise ValueError("release_commit must not include a -dirty suffix")
        return recorded

    @model_validator(mode="after")
    def _complete_release_provenance(self) -> Self:
        """Require release commit, tag, and content assessment together or not at all."""
        release_values = (self.release_commit, self.release_tag, self.protected_content_modified)
        if any(entry is not None for entry in release_values) and any(
            entry is None for entry in release_values
        ):
            raise ValueError(
                "release_commit, release_tag, and protected_content_modified must all be set "
                "or all be null"
            )
        return self
