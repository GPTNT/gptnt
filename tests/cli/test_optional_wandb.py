"""Ensure that `wandb` is a genuinely optional extra.

`wandb` is opt-in through a `gptnt[wandb]` extra, so every non-wandb code path must import and
run without it. The transitive imports (generic code -> wandb module) are lazy, so the default
`--source local` path never loads a wandb module.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from gptnt.experiments.ledger import Source
from gptnt.experiments.ledger.local import LocalLedger
from gptnt.experiments.ledger.resolve import resolve_ledger

# Every module reachable on a non-wandb code path; all must import with wandb uninstalled.
NON_WANDB_MODULES = (
    "gptnt.experiments.ledger.resolve",
    "gptnt.experiments.ledger",
    "gptnt.cli.run.command",
    "gptnt.cli.onboarding.generate_specs",
    "gptnt.cli.experiments.cleanup",
    "gptnt.cli.experiments.cleanup_wandb",
)

# The wandb integration modules: importing either runs `import wandb`, so non-wandb paths must not.
_WANDB_MODULES = ("gptnt.experiments.ledger.wandb", "gptnt.experiments.wandb_runs")


def _hide_wandb(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `import wandb` (and any cached transitive module) behave as if its not installed."""
    monkeypatch.setitem(sys.modules, "wandb", None)
    for name in _WANDB_MODULES:
        monkeypatch.delitem(sys.modules, name, raising=False)


def test_locked_modules_import_without_wandb() -> None:
    """In a fresh interpreter with wandb absent, every non-wandb module imports cleanly."""
    statements = [
        "import sys",
        "sys.modules['wandb'] = None",
        *(f"import {module}" for module in NON_WANDB_MODULES),
    ]
    code = "\n".join(statements)
    result = subprocess.run(  # noqa: S603 — fixed argv, no shell, test-only
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_resolve_ledger_local_never_touches_wandb(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The local source resolves a LocalLedger even with wandb unavailable."""
    _hide_wandb(monkeypatch)
    ledger = resolve_ledger(Source.local, output_dir=tmp_path)
    assert isinstance(ledger, LocalLedger)


def test_resolve_ledger_wandb_raises_without_wandb(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Selecting the wandb source without the extra installed raises ModuleNotFoundError."""
    _hide_wandb(monkeypatch)
    with pytest.raises(ModuleNotFoundError):
        _ = resolve_ledger(Source.wandb, output_dir=tmp_path)
