"""The shared check-result value object for `gptnt doctor` and `gptnt submission validate`.

A dependency-free home so a command can build and render findings without pulling in doctor's heavy
probes (httpx, psutil, the game client, hydra).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Self

CheckStatus = Literal["pass", "fail", "warn", "skip"]
"""How a check landed: `pass` ✓, `fail` ✗ (fails the run), `warn` ⚠ (reported, never fails), `skip`
⊘ (not applicable here, e.g. an X display on macOS)."""


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one check (doctor and `submission validate` share it).

    `detail` is what was found (shown always). `hint` is the fix and is shown on ✗/⚠. The
    per-status constructors are the preferred spelling — `CheckResult.failed("digest", …)` reads
    as the finding it is.
    """

    name: str
    status: CheckStatus
    detail: str = ""
    hint: str = ""

    @classmethod
    def passed(cls, name: str, detail: str = "") -> Self:
        """The check held."""
        return cls(name, "pass", detail=detail)

    @classmethod
    def failed(cls, name: str, detail: str = "", hint: str = "") -> Self:
        """The check found a real problem; the run fails."""
        return cls(name, "fail", detail=detail, hint=hint)

    @classmethod
    def warned(cls, name: str, detail: str = "", hint: str = "") -> Self:
        """Worth flagging, but never fails the run."""
        return cls(name, "warn", detail=detail, hint=hint)

    @classmethod
    def skipped(cls, name: str, detail: str = "") -> Self:
        """Not applicable here."""
        return cls(name, "skip", detail=detail)
