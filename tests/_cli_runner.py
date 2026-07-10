"""Minimal cyclopts CLI test driver (replaces typer's `CliRunner`).

Cyclopts has no `CliRunner`: an `App` is just callable. This runs an app on an argv list, captures
stdout+stderr (both cyclopts' help/error output and the commands' `rich` consoles write there), and
turns the `SystemExit` cyclopts raises on completion / `--help` / parse errors into an exit code —
mirroring `runner.invoke(...).exit_code` / `.output`.

Use this for parse-level and success-path assertions. For a command whose *failure* is the point,
call the function (or `pipeline` helper) directly and assert the raised exception with
`pytest.raises(...)` — that exception propagates rather than becoming an exit code.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cyclopts import App


@dataclass(frozen=True)
class CliResult:
    """The captured outcome of one CLI invocation."""

    exit_code: int
    output: str


def invoke_cli(app: App, argv: list[str]) -> CliResult:
    """Run `app` with `argv`, capturing combined stdout/stderr and the resulting exit code.

    Output is plain text: the `pytest_env` config sets `TTY_COMPATIBLE=0`, so the commands' `rich`
    consoles emit no ANSI escapes and a test can assert on the rendered text directly.
    """
    buffer = io.StringIO()
    exit_code = 0
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        try:
            app(argv)
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
    return CliResult(exit_code=exit_code, output=buffer.getvalue())
