"""The check-result value object and its four-state status.

A dependency-free module so findings can be built and rendered apart from the probes that produce
them (httpx, psutil, the game client, hydra). It is the shared vocabulary for every findings
command — `gptnt doctor`, `gptnt suite freeze`, and `gptnt submission validate`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Self

CheckStatus = Literal["pass", "fail", "warn", "skip"]
"""The four check statuses: `pass` ✓, `fail` ✗ (fails the run), `warn` ⚠ (reported, never fails),
`skip` ⊘ (not applicable here, e.g. an X display on macOS)."""


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one check, shared by `gptnt doctor` and `gptnt submission validate`.

    `detail` is what was found (shown always). `hint` is the fix and is shown on ✗/⚠. Prefer the
    per-status constructors: `CheckResult.failed("digest", …)` reads as the finding it is.
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
