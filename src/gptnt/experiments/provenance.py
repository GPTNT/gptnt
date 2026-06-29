from __future__ import annotations

import subprocess
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from pydantic import BaseModel, Field

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
def gptnt_edition() -> int:
    """Leading SemVer MAJOR — the comparability generation (0 pre-v1 or if unresolved)."""
    head = gptnt_version().split(".", 1)[0]
    return int(head) if head.isdigit() else 0


def _run_git(*args: str, git_timeout: float = 2) -> str | None:
    try:
        # `git` is resolved via PATH and only runs our own fixed subcommands (no shell, no input).
        completed = subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
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
    return f"{sha}-dirty" if is_dirty else sha


class ProvenanceMixin(BaseModel):
    """Single source of truth for run provenance fields, mixed into the records that carry it."""

    gptnt_version: str = Field(default_factory=gptnt_version)
    gptnt_edition: int = Field(default_factory=gptnt_edition)
    git_sha: str | None = Field(default_factory=git_sha)
