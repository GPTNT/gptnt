from __future__ import annotations

from contextlib import suppress
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()


def _should_kill_process(proc_info: dict[str, Any]) -> tuple[bool, str, str | None]:
    """Determine if process should be killed and return its type and identifier.

    Returns:
        Tuple of (should_kill, process_type, pid_str).
    """
    cmdline = " ".join(proc_info["cmdline"] or [])
    name_lower = proc_info["name"].lower()
    pid = str(proc_info["pid"])

    # Kill Python processes running gptnt entrypoints
    if "python" in name_lower and "gptnt.interactive.entrypoints" in cmdline:
        return True, "gptnt player", pid

    # Kill ktane processes
    if "ktane" in name_lower:
        return True, "ktane game", pid

    return False, "", None


def _print_killed_processes(killed_processes: list[tuple[str, str]]) -> None:
    table = Table(title="Killed Processes", show_header=True, box=None)
    table.add_column("Type", style="cyan", no_wrap=True)
    table.add_column("PID", style="magenta", justify="right")

    for proc_type, pid in killed_processes:
        table.add_row(proc_type, pid)

    console.print()
    console.print(table)


def force_kill() -> None:
    """Force kill all game and player processes.

    Force clean up any leftover processes from a previous run, especially if they are stuck and not
    responding to normal termination.
    """
    import psutil

    console.print("\n[bold yellow]🔍 Scanning for processes...[/bold yellow]")

    killed_processes: list[tuple[str, str]] = []

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            should_kill, proc_type, pid = _should_kill_process(proc.info)
            if should_kill and pid:
                with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                    proc.kill()
                    killed_processes.append((proc_type, pid))

    if killed_processes:
        _print_killed_processes(killed_processes)
        console.print(f"\n[bold green]✓ Killed {len(killed_processes)} process(es)[/bold green]\n")
    else:
        console.print("[dim]No matching processes found[/dim]\n")
