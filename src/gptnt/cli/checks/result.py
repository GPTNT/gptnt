"""The check-result value object and its four-state status."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Self

CheckStatus = Literal["pass", "fail", "warn", "skip"]
"""The four check statuses.

`fail` fails the run, `warn` is reported but never fails, and `skip`
marks a check not applicable here (an X display on macOS). Glyphs live in `render.GLYPHS`.
"""


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
    def skipped(cls, name: str, detail: str = "", hint: str = "") -> Self:
        """Not applicable here."""
        return cls(name, "skip", detail=detail, hint=hint)
