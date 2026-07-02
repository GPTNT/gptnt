from __future__ import annotations

import signal
from collections import Counter
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import anyio
import httpx
import structlog

from gptnt.common.async_ops import periodic
from gptnt.common.runtime_settings import RuntimeSettings
from gptnt.interactive.orchestration.orchestrator import (
    ProcessOrchestrator,
    abort_on_shutdown,
    fail_and_terminate,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from gptnt.specification import PlayerSpec


logger = structlog.get_logger()
runtime_settings = RuntimeSettings()


async def spawn_rooms(
    orch: ProcessOrchestrator, num_rooms: int, displays: list[int] | None
) -> None:
    """Spawn the requested number of game rooms, each in its own process to run in parallel.

    When `displays` is given, rooms are spread round-robin across those X display numbers (one
    display per GPU in a headless multi-GPU setup). When it is `None`, `DISPLAY` is left untouched
    so each room inherits the ambient `$DISPLAY` from the environment.
    """
    logger.info("Starting game rooms", count=num_rooms)

    for room_idx in range(num_rooms):
        if orch.shutdown_event.is_set():
            break
        extra_env = None
        if displays is not None:
            extra_env = {"DISPLAY": f":{displays[room_idx % len(displays)]}"}
        _ = await orch.spawn(  # noqa: WPS476
            f"game__{room_idx}",
            ["uv", "run", "python", "-u", "-m", "gptnt.interactive.entrypoints.run_game_instance"],
            extra_env=extra_env,
        )
        _ = await anyio.sleep(2)  # noqa: WPS476

    await abort_on_shutdown(orch)


async def _wait_for_em_ready(
    orch: ProcessOrchestrator, *, fail_after: float = 60.0, interval: float = 0.5
) -> None:
    """Poll the experiment manager's /health endpoint until it is ready, or fail loudly.

    Replaces a blind fixed sleep so `run` starts as soon as the EM is actually up, and surfaces a
    clear error if it never binds or dies during startup.
    """
    url = runtime_settings.em_health_url
    logger.info("Waiting for experiment manager to be ready")

    async with httpx.AsyncClient() as client:
        with anyio.fail_after(fail_after):
            async for _ in periodic(interval):
                await abort_on_shutdown(orch)
                orch.poll_all()
                if failed := orch.any_failed():
                    await fail_and_terminate(orch, failed)

                # See if its ready, otherwise try again
                try:
                    response = await client.get(url, timeout=2.0)
                except httpx.HTTPError:
                    continue

                if response.is_success:
                    logger.info("Experiment manager is ready")
                    return

    logger.error("Experiment manager did not become ready", timeout_seconds=fail_after)
    await orch.terminate_all()
    raise RuntimeError(f"Experiment manager did not become ready within {fail_after:.0f}s.")


async def spawn_experiment_manager(orch: ProcessOrchestrator) -> None:
    """Spawn the experiment manager process and wait for it to be ready."""
    logger.info("Starting experiment manager")
    _ = await orch.spawn(
        "experiment_manager",
        [
            "uv",
            "run",
            "python",
            "-u",
            "-m",
            "gptnt.interactive.entrypoints.run_experiment_manager",
        ],
    )

    await abort_on_shutdown(orch)
    await _wait_for_em_ready(orch)


def _build_player_command(player: PlayerSpec) -> list[str]:
    """Build the `run_player` entrypoint command for one player spec."""
    command = [
        "uv",
        "run",
        "python",
        "-u",
        "-m",
        "gptnt.interactive.entrypoints.run_player",
        f"player={player.player}",
    ]
    if player.provider:
        command.append(f"player/provider={player.provider}")
    return command


async def spawn_players(
    orch: ProcessOrchestrator, players: list[PlayerSpec], output_dir: Path
) -> None:
    """Spawn the requested players, each in its own process to run in parallel."""
    logger.info("Starting players", count=sum(player.count for player in players))
    player_counters: Counter[str] = Counter()
    for player in players:
        for _ in range(player.count):
            # Break if we need to shutdown during startup
            if orch.shutdown_event.is_set():
                break

            idx = player_counters.get(player.player, 0)
            player_counters[player.player] += 1
            _ = await orch.spawn(  # noqa: WPS476
                f"{player.player}__{idx}",
                _build_player_command(player),
                extra_env={"EXPERIMENT_RECORDER_OUTPUTS": str(output_dir)},
            )
            await anyio.sleep(1)  # noqa: WPS476

    await abort_on_shutdown(orch)


@asynccontextmanager
async def handle_signals(orch: ProcessOrchestrator) -> AsyncGenerator[None]:
    """Handle any shutdown signals."""
    # Signal handling
    shutdown_requested = False

    def _signal_handler(sig: int, _frame: object) -> None:  # noqa: WPS430
        nonlocal shutdown_requested  # noqa: WPS420
        if not shutdown_requested:
            shutdown_requested = True
            logger.warning("Received shutdown signal", signal=signal.Signals(sig).name)
            orch.shutdown_event.set()

    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)
    _ = signal.signal(signal.SIGINT, _signal_handler)
    _ = signal.signal(signal.SIGTERM, _signal_handler)

    try:  # noqa: WPS243
        yield
    finally:
        orch.close_log_files()
        _ = signal.signal(signal.SIGINT, original_sigint)
        _ = signal.signal(signal.SIGTERM, original_sigterm)
