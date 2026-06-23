"""Resolve every lazily-registered command, catching broken import-path strings.

Lazy registration (`app.command("module.path:func", ...)`) trades Typer's eager-import safety for a
fast `--help`: a typo in an import-path string is invisible until that command is invoked. These
tests restore the safety net — they import-resolve every registered command (top-level and nested),
and render each command's own `--help` (which resolves its signature too). A bad path or a broken
`Parameter` annotation fails here instead of in a user's terminal.

Unlike `test_lazy_imports`, this test DOES import the heavy command modules — that is the point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from gptnt.cli.__main__ import build_app

from tests._cli_runner import invoke_cli

if TYPE_CHECKING:
    from cyclopts import App


def _command_names(app: App) -> list[str]:
    """The real subcommand names registered on `app` (excluding the `--help`/`--version` meta)."""
    return sorted(name for name in app if not name.startswith("-"))


def _all_command_paths() -> list[tuple[str, ...]]:
    """Every invocable command path, recursing one level into sub-apps (e.g. `new`, `statics`)."""
    app = build_app()
    paths: list[tuple[str, ...]] = []
    for name in _command_names(app):
        resolved = app[name]  # resolving the lazy spec imports the target module
        nested = _command_names(resolved)
        if nested:
            paths.extend((name, child) for child in nested)
        else:
            paths.append((name,))
    return paths


COMMAND_PATHS = _all_command_paths()


def test_every_command_resolves() -> None:
    """Building the app and resolving each command imports a real callable for every leaf."""
    app = build_app()
    for path in COMMAND_PATHS:
        target = app[path[0]]
        for segment in path[1:]:
            target = target[segment]
        assert callable(target.default_command), f"{' '.join(path)} did not resolve to a callable"


@pytest.mark.parametrize("path", COMMAND_PATHS, ids=" ".join)
def test_command_help_renders(path: tuple[str, ...]) -> None:
    """`gptnt <command> --help` resolves the command's signature and exits 0."""
    result = invoke_cli(build_app(), [*path, "--help"])
    assert result.exit_code == 0, result.output
