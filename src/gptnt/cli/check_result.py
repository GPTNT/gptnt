"""The check-result value object and its four-state status.

A dependency-free module so findings can be built and rendered apart from doctor's probes (httpx,
psutil, the game client, hydra).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CheckStatus = Literal["pass", "fail", "warn", "skip"]
"""The four check statuses: `pass` ✓, `fail` ✗ (fails the run), `warn` ⚠ (reported, never fails),
`skip` ⊘ (not applicable here, e.g. an X display on macOS)."""


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one check.

    `detail` is what was found (shown always). `hint` is the fix and is shown on ✗/⚠.
    """

    name: str
    status: CheckStatus
    detail: str = ""
    hint: str = ""
