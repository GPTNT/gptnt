from __future__ import annotations

import signal
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import anyio
import typer
from rich.console import Console

from gptnt.cli.orchestrator import ProcessOrchestrator, monitor_interactive, monitor_status

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from gptnt.cli.models import PlayerSpec


console = Console()


async def _spawn_rooms(orch: ProcessOrchestrator, num_rooms: int, display_num: int) -> None:
    console.print(f"\n[bold]Starting {num_rooms} game room(s)...[/bold]")
    for room_idx in range(num_rooms):
        if orch.shutdown_event.is_set():
            break
        _ = await orch.spawn(  # noqa: WPS476
            f"game_{room_idx}",
            ["uv", "run", "python", "-u", "src/gptnt/entrypoints/run_game_instance.py"],
            extra_env={"DISPLAY": f":{display_num}"},
        )
        _ = await anyio.sleep(2)  # noqa: WPS476

    if orch.shutdown_event.is_set():
        await orch.terminate_all()
        raise typer.Exit(code=1)


async def _spawn_experiment_manager(orch: ProcessOrchestrator) -> None:
    console.print("[bold]Starting experiment manager...[/bold]")
    _ = await orch.spawn(
        "experiment_manager",
        ["uv", "run", "python", "-u", "src/gptnt/entrypoints/run_experiment_manager.py"],
    )

    if orch.shutdown_event.is_set():
        await orch.terminate_all()
        raise typer.Exit(code=1)  # noqa: WPS204

    console.print("  Waiting 5s for experiment manager to initialise...")
    await anyio.sleep(5)


async def _spawn_players(
    orch: ProcessOrchestrator, players: list[PlayerSpec], output_dir: Path
) -> None:
    console.print(
        f"\n[bold]Starting {sum(player.count for player in players)} player(s)...[/bold]"
    )
    player_counters: dict[str, int] = {}
    for player in players:
        for _ in range(player.count):
            if orch.shutdown_event.is_set():
                break
            idx = player_counters.get(player.model_name, 0)
            player_counters[player.model_name] = idx + 1
            _ = await orch.spawn(  # noqa: WPS476
                f"{player.model_name}_{idx}",
                [
                    "uv",
                    "run",
                    "python",
                    "-u",
                    "src/gptnt/entrypoints/run_player.py",
                    f"model={player.model_name}",
                ],
                extra_env={"EXPERIMENT_RECORDER_OUTPUTS": str(output_dir)},
            )
            await anyio.sleep(1)  # noqa: WPS476

    if orch.shutdown_event.is_set():
        await orch.terminate_all()
        raise typer.Exit(code=1)


@asynccontextmanager
async def handle_signals(orch: ProcessOrchestrator) -> AsyncGenerator[None]:
    """Handle any shutdown signals."""
    # Signal handling
    shutdown_requested = False

    def _signal_handler(sig: int, _frame: object) -> None:  # noqa: WPS430
        nonlocal shutdown_requested  # noqa: WPS420
        if not shutdown_requested:
            shutdown_requested = True
            console.print(
                f"\n[yellow]Received signal {signal.Signals(sig).name}, shutting down...[/yellow]"
            )
            orch.shutdown_event.set()

    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)
    _ = signal.signal(signal.SIGINT, _signal_handler)
    _ = signal.signal(signal.SIGTERM, _signal_handler)

    try:  # noqa: WPS501, WPS243
        yield
    finally:
        orch.close_log_files()
        _ = signal.signal(signal.SIGINT, original_sigint)
        _ = signal.signal(signal.SIGTERM, original_sigterm)


async def _do_spawn_and_monitor(
    orch: ProcessOrchestrator,
    num_rooms: int,
    players: list[PlayerSpec],
    display_num: int,
    output_dir: Path,
) -> None:
    """Spawn all processes and then monitor them."""
    await _spawn_experiment_manager(orch)
    await _spawn_rooms(orch, num_rooms, display_num)
    await _spawn_players(orch, players, output_dir)


async def run_throw(  # noqa: WPS213
    orch: ProcessOrchestrator,
    num_rooms: int,
    players: list[PlayerSpec],
    display_num: int,
    output_dir: Path,
) -> None:
    """Core orchestration: spawn processes and monitor until completion or failure."""
    if orch.interactive:
        async with anyio.create_task_group() as tg:
            orch.stream_tasks = tg
            await _do_spawn_and_monitor(orch, num_rooms, players, display_num, output_dir)
            await monitor_interactive(orch)
            tg.cancel_scope.cancel()
    else:
        await _do_spawn_and_monitor(orch, num_rooms, players, display_num, output_dir)
        await monitor_status(orch)

    # Success
    console.print()
    console.rule("[bold green]All processes completed successfully[/bold green]")
    console.print(f"  Logs saved to:              {orch.logs_dir}")
    console.print(f"  Experiment outputs saved to: {orch.output_dir}")
