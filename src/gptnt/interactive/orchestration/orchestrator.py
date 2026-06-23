from __future__ import annotations

import contextlib
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

import anyio
import structlog

if TYPE_CHECKING:
    from collections.abc import Callable
    from io import TextIOWrapper
    from pathlib import Path

    from anyio.abc import Process

logger = structlog.get_logger()


class ProcessStatus(Enum):
    """Status of a tracked process."""

    RUNNING = auto()
    DONE = auto()
    FAILED = auto()
    KILLED = auto()


@dataclass
class TrackedProcess:
    """A tracked subprocess with metadata."""

    name: str
    process: Process
    log_path: Path
    log_file: TextIOWrapper
    prefix_color: str = "cyan"
    status: ProcessStatus = ProcessStatus.RUNNING
    exit_code: int | None = None


@dataclass
class ProcessOrchestrator:
    """Manages all spawned processes and their lifecycle.

    The engine is rendering-agnostic: operational events go through `structlog`, and the live
    child-log stream is decoupled via `on_spawn`. When set, `spawn()` invokes it with each freshly
    spawned process instead of doing any rendering itself, so the CLI can tee/colour the output
    (`cli/run`) while the engine only owns the process lifecycle.
    """

    logs_dir: Path
    output_dir: Path
    env_base: dict[str, str]
    interactive: bool = False
    processes: list[TrackedProcess] = field(default_factory=list)
    shutdown_event: anyio.Event = field(default_factory=anyio.Event)
    on_spawn: Callable[[TrackedProcess], None] | None = field(default=None, repr=False)

    async def spawn(
        self, name: str, cmd: list[str], extra_env: dict[str, str] | None = None
    ) -> TrackedProcess:
        """Spawn a subprocess, redirecting stdout+stderr to a log file.

        In interactive mode, output is piped so the registered `on_spawn` handler can tee it to
        both the log file and the console with a coloured name prefix (like `docker compose`).
        """
        env = {**self.env_base, **(extra_env or {})}
        log_path = self.logs_dir / f"{name}.log"
        log_file_handler = log_path.open("w")

        process = await anyio.open_process(
            cmd,
            env={**os.environ, **env},
            stdout=subprocess.PIPE if self.interactive else log_file_handler.fileno(),
            stderr=subprocess.STDOUT if self.interactive else log_file_handler.fileno(),
        )

        tracked = TrackedProcess(
            name=name, process=process, log_path=log_path, log_file=log_file_handler
        )
        self.processes.append(tracked)
        logger.info("Started process", name=name, pid=process.pid, log_path=str(log_path))

        if self.interactive and self.on_spawn is not None:
            self.on_spawn(tracked)

        return tracked

    def poll_all(self) -> None:
        """Update status for all tracked processes (non-blocking)."""
        for tp in self.processes:
            if tp.status != ProcessStatus.RUNNING:
                continue
            rc = tp.process.returncode
            if rc is not None:
                tp.exit_code = rc
                tp.status = ProcessStatus.DONE if rc == 0 else ProcessStatus.FAILED

    def any_failed(self) -> TrackedProcess | None:
        """Return the first failed process, if any."""
        return next((tp for tp in self.processes if tp.status == ProcessStatus.FAILED), None)

    def all_done(self) -> bool:
        """Return True if every process has exited."""
        return all(
            tp.status in (ProcessStatus.DONE, ProcessStatus.FAILED) for tp in self.processes
        )

    def running_processes(self) -> list[TrackedProcess]:
        """Return processes still running."""
        return [tp for tp in self.processes if tp.status == ProcessStatus.RUNNING]

    async def terminate_all(self, grace_period: float = 35.0) -> None:
        """Send SIGTERM to all running processes, wait, then SIGKILL stragglers."""
        running = self.running_processes()
        if not running:
            return

        logger.warning("Terminating processes", count=len(running))
        for tp in running:
            with contextlib.suppress(ProcessLookupError):
                tp.process.terminate()

        deadline = anyio.current_time() + grace_period
        while anyio.current_time() < deadline:
            self.poll_all()
            if not self.running_processes():
                break
            await anyio.sleep(1)

        for tp in self.running_processes():
            logger.warning("Force-killing process", name=tp.name, pid=tp.process.pid)
            with contextlib.suppress(ProcessLookupError):
                tp.process.kill()
            tp.status = ProcessStatus.KILLED

    def close_log_files(self) -> None:
        """Close all open log file handles."""
        for tp in self.processes:
            with contextlib.suppress(Exception):
                tp.log_file.close()


async def fail_and_terminate(orch: ProcessOrchestrator, failed: TrackedProcess) -> None:
    """Report a process failure, tear down the cluster, and exit non-zero.

    The single "log failure → terminate → exit" path shared by the spawn and monitor steps so a
    crashed child never leaves the run idling forever.
    """
    logger.error(
        "Process failed",
        name=failed.name,
        pid=failed.process.pid,
        exit_code=failed.exit_code,
        log_path=str(failed.log_path),
    )
    await orch.terminate_all()
    raise RuntimeError(f"Process '{failed.name}' failed with exit code {failed.exit_code}.")


async def abort_on_shutdown(orch: ProcessOrchestrator) -> None:
    """Tear down and exit if a shutdown signal was requested mid-spawn."""
    if orch.shutdown_event.is_set():
        await orch.terminate_all()
        raise RuntimeError("Shutdown requested during startup; cluster torn down.")
