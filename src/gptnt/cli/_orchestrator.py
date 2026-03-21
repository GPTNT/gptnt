from __future__ import annotations

import contextlib
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum, auto
from itertools import cycle
from typing import TYPE_CHECKING

import anyio
import typer
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from io import TextIOWrapper
    from pathlib import Path

    from anyio.abc import Process, TaskGroup

console = Console()

# Rotating colors for interactive log prefixes
_PREFIX_COLORS = cycle(
    [
        "cyan",
        "green",
        "magenta",
        "yellow",
        "blue",
        "red",
        "bright_cyan",
        "bright_green",
        "bright_magenta",
        "bright_yellow",
    ]
)


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
    """Manages all spawned processes and their lifecycle."""

    logs_dir: Path
    output_dir: Path
    env_base: dict[str, str]
    interactive: bool = False
    processes: list[TrackedProcess] = field(default_factory=list)
    shutdown_event: anyio.Event = field(default_factory=anyio.Event)

    stream_tasks: TaskGroup | None = field(default=None, repr=False)

    async def spawn(
        self, name: str, cmd: list[str], extra_env: dict[str, str] | None = None
    ) -> TrackedProcess:
        """Spawn a subprocess, redirecting stdout+stderr to a log file.

        In interactive mode, output is piped and tee'd to both the log file and the console with a
        coloured name prefix (like `docker compose`).
        """
        env = {**self.env_base, **(extra_env or {})}
        log_path = self.logs_dir / f"{name}.log"
        log_file_handler = log_path.open("w")
        color = next(_PREFIX_COLORS)

        process = await anyio.open_process(
            cmd,
            env={**os.environ, **env},
            stdout=subprocess.PIPE if self.interactive else log_file_handler.fileno(),
            stderr=subprocess.STDOUT if self.interactive else log_file_handler.fileno(),
        )

        tracked = TrackedProcess(
            name=name,
            process=process,
            log_path=log_path,
            log_file=log_file_handler,
            prefix_color=color,
        )
        self.processes.append(tracked)
        console.print(f"  [green]Started[/green] {name} (PID: {process.pid}, Log: {log_path})")

        if self.interactive and self.stream_tasks is not None:
            self.stream_tasks.start_soon(_stream_output, tracked)

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

        console.print(f"\n[yellow]Terminating {len(running)} process(es)...[/yellow]")
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
            console.print(f"  [red]Force-killing[/red] {tp.name} (PID: {tp.process.pid})")
            with contextlib.suppress(ProcessLookupError):
                tp.process.kill()
            tp.status = ProcessStatus.KILLED

    def close_log_files(self) -> None:
        """Close all open log file handles."""
        for tp in self.processes:
            with contextlib.suppress(Exception):
                tp.log_file.close()


def build_status_table(orch: ProcessOrchestrator) -> Table:
    """Build a Rich table showing current process status."""
    table = Table(title="Process Status", show_lines=False, expand=True)
    table.add_column("Name", style="bold")
    table.add_column("PID", justify="right")
    table.add_column("Status")
    table.add_column("Log File", style="dim")

    for tp in orch.processes:
        match tp.status:
            case ProcessStatus.RUNNING:
                status = Text("running", style="green")
            case ProcessStatus.DONE:
                status = Text("done", style="blue")
            case ProcessStatus.FAILED:
                status = Text(f"FAILED (exit {tp.exit_code})", style="bold red")
            case ProcessStatus.KILLED:
                status = Text("killed", style="yellow")

        table.add_row(
            tp.name, str(tp.process.pid) if tp.process.pid else "?", status, str(tp.log_path)
        )
    return table


async def monitor_status(orch: ProcessOrchestrator) -> None:  # noqa: WPS231
    """Monitor the status of all the processes."""
    console.print()
    console.rule("[bold]Monitoring processes[/bold]")
    with Live(build_status_table(orch), console=console, refresh_per_second=1) as live:
        while True:
            orch.poll_all()
            live.update(build_status_table(orch))

            failed = orch.any_failed()
            if failed:
                live.stop()
                console.print(
                    f"\n[bold red]ERROR:[/bold red] Process '{failed.name}' (PID {failed.process.pid}) "
                    f"failed with exit code {failed.exit_code}."
                )
                console.print(f"  Check logs at: {failed.log_path}")
                await orch.terminate_all()
                raise typer.Exit(code=1)

            if orch.all_done():
                break

            if orch.shutdown_event.is_set():
                await orch.terminate_all()
                live.stop()
                raise typer.Exit(code=1)

            await anyio.sleep(1)


async def _stream_output(tp: TrackedProcess, *, max_name_len: int = 20) -> None:
    """Read lines from a piped process and tee to console + log file.

    Each line is prefixed with the process name in its assigned colour, similar to `docker compose`
    output.
    """
    assert tp.process.stdout is not None
    padded = tp.name[:max_name_len].ljust(max_name_len)
    prefix = f"[{tp.prefix_color}]{padded}[/{tp.prefix_color}] | "

    async for raw_line in tp.process.stdout:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
        console.print(f"{prefix}{line}", highlight=False)
        _ = tp.log_file.write(f"{line}\n")
        tp.log_file.flush()


async def monitor_interactive(orch: ProcessOrchestrator) -> None:  # noqa: WPS231
    """Monitor processes in interactive mode — stream output and watch for failures.

    The streaming tasks are started by ``spawn()`` into the task group. This function just polls
    process status until everything completes or something fails.
    """
    console.print()
    console.rule("[bold]Monitoring processes (interactive)[/bold]")
    console.print("You can safely detach from tmux now.\n")

    while True:
        orch.poll_all()

        failed = orch.any_failed()
        if failed:
            console.print(
                f"\n[bold red]ERROR:[/bold red] Process '{failed.name}' (PID {failed.process.pid}) "
                f"failed with exit code {failed.exit_code}."
            )
            console.print(f"  Check logs at: {failed.log_path}")
            await orch.terminate_all()
            raise typer.Exit(code=1)

        if orch.all_done():
            break

        if orch.shutdown_event.is_set():
            await orch.terminate_all()
            raise typer.Exit(code=1)

        await anyio.sleep(1)
