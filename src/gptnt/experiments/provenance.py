from __future__ import annotations

import subprocess
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, Field, field_validator

# Used when the package metadata or git state can't be resolved (e.g. an exotic install layout).
UNKNOWN_VERSION = "0.0.0"
# Marker appended to a recorded sha when the working tree had uncommitted changes.
DIRTY_SUFFIX = "-dirty"
_MODULE_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def gptnt_version() -> str:
    """Resolved gptnt version, e.g. `0.13.2` or `0.13.2.dev3+g<sha>` between releases."""
    try:
        return version("gptnt")
    except PackageNotFoundError:
        return UNKNOWN_VERSION


def _run_git(*args: str, git_timeout: float = 2) -> str | None:
    try:
        # `git` is resolved via PATH and only runs our own fixed subcommands (no shell, no input).
        completed = subprocess.run(  # noqa: S603
            ["git", *args],
            cwd=_MODULE_DIR,
            capture_output=True,
            text=True,
            check=False,
            timeout=git_timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


@lru_cache(maxsize=1)
def git_sha() -> str | None:
    """Current commit at record time, with a `-dirty` suffix if the tree has uncommitted changes.

    Read live so a run is traceable to the exact code that produced it; `None` when git is
    unavailable (e.g. installed without a working tree), in which case rely on the version string.
    """
    sha = _run_git("rev-parse", "HEAD")
    if sha is None:
        return None
    is_dirty = bool(_run_git("status", "--porcelain"))
    return f"{sha}{DIRTY_SUFFIX}" if is_dirty else sha


def is_dirty_sha(sha: str) -> bool:
    """Whether a recorded git sha ends with the dirty-tree marker."""
    return sha.endswith(DIRTY_SUFFIX)


def is_valid_version(recorded: str | None) -> bool:
    """Whether a recorded version is resolvable.

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
    """The gptnt version and git sha resolved when a record is written."""

    gptnt_version: str = Field(default_factory=gptnt_version)
    git_sha: str | None = Field(default_factory=git_sha)

    @property
    def is_dirty(self) -> bool:
        """Whether the recorded git sha ends with the dirty-tree marker."""
        return self.git_sha is not None and is_dirty_sha(self.git_sha)

    @field_validator("gptnt_version")
    @classmethod
    def _reject_unknown_version(cls, recorded: str) -> str:
        """Reject an explicitly-supplied version that is blank or the unknown marker.

        The `gptnt_version` default_factory is not run through this (pydantic skips default
        validation), so the `UNKNOWN_VERSION` fallback still stands for a genuinely unresolvable
        install. A version supplied from a record, footer, or manifest is validated.
        """
        if not is_valid_version(recorded):
            raise ValueError(
                f"gptnt_version {recorded!r} is not a valid version "
                "(must be a real semantic version, not blank or the unknown marker)"
            )
        return recorded
