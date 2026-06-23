"""Rich rendering for the `gptnt run` supervisor: status table, monitors, and child-log tee.

These consume only the orchestrator's public state (`poll_all` / `any_failed` / `all_done` /
`terminate_all`), so all presentation lives here in the CLI layer while the engine
(`gptnt.interactive.orchestration`) stays rendering-agnostic.
"""

from __future__ import annotations

from itertools import cycle

import anyio
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

from gptnt.interactive.orchestration import (
    ProcessOrchestrator,
    ProcessStatus,
    TrackedProcess,
    fail_and_terminate,
)

console = Console()

# Rotating colours for interactive log prefixes (docker-compose style).
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


async def monitor_status(orch: ProcessOrchestrator) -> None:
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
                await fail_and_terminate(orch, failed)

            if orch.all_done():
                break

            if orch.shutdown_event.is_set():
                live.stop()
                await orch.terminate_all()
                raise RuntimeError("Shutdown requested; cluster torn down.")

            await anyio.sleep(1)


async def render_stream(tracked: TrackedProcess, *, max_name_len: int = 20) -> None:
    """Read lines from a piped process and tee them to the console + log file.

    Each line is prefixed with the process name in a rotating colour, like `docker compose`. This
    is the handler the CLI registers as the orchestrator's `on_spawn` in interactive mode.
    """
    assert tracked.process.stdout is not None
    tracked.prefix_color = next(_PREFIX_COLORS)
    padded = tracked.name[:max_name_len].ljust(max_name_len)
    prefix = f"[{tracked.prefix_color}]{padded}[/{tracked.prefix_color}] | "

    async for raw_line in tracked.process.stdout:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
        console.print(f"{prefix}{line}", highlight=False)
        _ = tracked.log_file.write(f"{line}\n")
        tracked.log_file.flush()


async def monitor_interactive(orch: ProcessOrchestrator) -> None:  # noqa: WPS231
    """Monitor processes in interactive mode — output streams live; watch for completion/failure.

    The per-process streaming tasks are started via the orchestrator's `on_spawn` callback (set by
    the pipeline); this loop only polls status until everything finishes, something fails, or a
    shutdown is requested.
    """
    console.print()
    console.rule("[bold]Monitoring processes (interactive)[/bold]")
    while True:
        orch.poll_all()

        failed = orch.any_failed()
        if failed:
            await fail_and_terminate(orch, failed)

        if orch.all_done():
            break

        if orch.shutdown_event.is_set():
            await orch.terminate_all()
            raise RuntimeError("Shutdown requested; cluster torn down.")

        await anyio.sleep(1)
