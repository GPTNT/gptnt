"""Spawn and teardown of real subprocesses through `ProcessOrchestrator`.

These use trivial `python -c` children, not the real game rooms or players, so they cover the
process-lifecycle machinery (`gptnt run` relies on it to reclaim children) without the KTANE binary
or an X display. Driving the full `gptnt run` against the real binary is a `requires_game` concern.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import anyio
import pytest

from gptnt.interactive.orchestration.orchestrator import ProcessOrchestrator, ProcessStatus

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.anyio

# A child that traps SIGTERM and keeps running, so only SIGKILL can reclaim it.
_IGNORES_SIGTERM = "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"


async def _drain(orchestrator: ProcessOrchestrator, *, fail_after: float = 10.0) -> None:
    """Poll until every tracked process has exited."""
    with anyio.fail_after(fail_after):
        while not orchestrator.all_done():
            orchestrator.poll_all()
            await anyio.sleep(0.05)


async def _reap(orchestrator: ProcessOrchestrator) -> None:
    """Wait on every child so none is left as a zombie, then close the log handles."""
    with anyio.fail_after(10):
        for tracked in orchestrator.processes:
            _ = await tracked.process.wait()
    orchestrator.close_log_files()


async def test_spawn_runs_to_completion(tmp_path: Path) -> None:
    """Two short-lived children run and are tracked to a clean exit."""
    orchestrator = ProcessOrchestrator(logs_dir=tmp_path, output_dir=tmp_path, env_base={})
    first = await orchestrator.spawn("first", [sys.executable, "-c", "pass"])
    second = await orchestrator.spawn("second", [sys.executable, "-c", "pass"])

    await _drain(orchestrator)

    assert first.status == ProcessStatus.DONE
    assert second.status == ProcessStatus.DONE
    assert first.exit_code == 0
    assert not orchestrator.running_processes()
    await _reap(orchestrator)


async def test_terminate_force_kills_straggler(tmp_path: Path) -> None:
    """A child that ignores SIGTERM is force-killed, so nothing runs past the grace period."""
    orchestrator = ProcessOrchestrator(logs_dir=tmp_path, output_dir=tmp_path, env_base={})
    _ = await orchestrator.spawn("normal", [sys.executable, "-c", "import time; time.sleep(60)"])
    stubborn = await orchestrator.spawn("stubborn", [sys.executable, "-c", _IGNORES_SIGTERM])
    # Give the stubborn child a moment to install its SIGTERM handler before terminating.
    await anyio.sleep(0.5)

    with anyio.fail_after(15):
        await orchestrator.terminate_all(grace_period=2)

    assert not orchestrator.running_processes(), "a process survived teardown"
    assert stubborn.status == ProcessStatus.KILLED
    await _reap(orchestrator)


async def test_any_failed_detects_nonzero_exit(tmp_path: Path) -> None:
    """A child that exits non-zero is surfaced by `any_failed`, the signal the pipeline acts on."""
    orchestrator = ProcessOrchestrator(logs_dir=tmp_path, output_dir=tmp_path, env_base={})
    healthy = await orchestrator.spawn("healthy", [sys.executable, "-c", "pass"])
    broken = await orchestrator.spawn("broken", [sys.executable, "-c", "raise SystemExit(1)"])

    await _drain(orchestrator)

    assert orchestrator.any_failed() is broken
    assert broken.status == ProcessStatus.FAILED
    assert healthy.status == ProcessStatus.DONE
    await _reap(orchestrator)
