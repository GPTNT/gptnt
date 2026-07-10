"""`gptnt doctor` game/mod checks: the KTANE binary, mod files, X display, and the game spawn."""

from __future__ import annotations

import contextlib
import os
import platform
import sys
from pathlib import Path

import anyio
import httpx

from gptnt.cli.checks.result import CheckResult
from gptnt.common.paths import Paths
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.executable import (
    GameNotFoundError,
    ModNotFoundError,
    ensure_mod_exists,
    get_executable_path,
)
from gptnt.ktane.process_manager import GameProcessManager
from gptnt.ktane.state.game import GameState

paths = Paths()

MOD_LOAD_TIMEOUT = 45.0
MOD_LOAD_POLL = 1.0
MOD_LOAD_CHECK = "Mod loads (game spawn)"


def check_game_binary(*, name: str = "Game binary") -> CheckResult:
    """Resolve the per-OS game executable under `paths.ktane`."""
    layout_hint = (
        f"Copy the KTANE build into {paths.ktane} "
        "(Linux: *.x86_64 + ktane_Data/; macOS: *.app; Windows: *.exe + ktane_Data/)."
    )
    try:
        executable = get_executable_path()
    except (GameNotFoundError, RuntimeError) as exc:  # RuntimeError == unsupported OS
        return CheckResult.failed(name, str(exc), layout_hint)
    return CheckResult.passed(name, str(executable))


def check_mod_files(*, name: str = "Mod files") -> CheckResult:
    """Cheap on-disk check that the 'Gptnt Plays' mod directory exists."""
    hint = f"Install the 'Gptnt Plays' mod under {paths.ktane / 'mods'}."
    try:
        _ = ensure_mod_exists()
    except ModNotFoundError as exc:
        return CheckResult.failed(name, str(exc), hint)
    return CheckResult.passed(name, "'Gptnt Plays' present")


def check_display(
    *,
    name: str = "Display (X)",
    startx_hint: str = "Start a GPU-backed X server: uv run python scripts/startx.py",
) -> CheckResult:
    """On Linux, confirm an X display is available; elsewhere it is not required."""
    if sys.platform != "linux":
        return CheckResult.skipped(name, f"not required on {platform.system()}")

    display = os.environ.get("DISPLAY", "")
    if not display:
        return CheckResult.failed(name, "$DISPLAY is not set", startx_hint)

    display_num = display.rsplit(":", 1)[-1].split(".")[0]
    socket_path = Path(f"/tmp/.X11-unix/X{display_num}")  # noqa: S108  (standard X socket location)
    if socket_path.exists():
        return CheckResult.passed(name, f"using existing $DISPLAY={display}")
    return CheckResult.warned(
        name,
        f"$DISPLAY={display} set but {socket_path} not found",
        f"If this is a remote/TCP display it may still work; otherwise: {startx_hint}",
    )


async def check_mod_load(
    *,
    name: str = MOD_LOAD_CHECK,
    load_timeout: float = MOD_LOAD_TIMEOUT,
    poll: float = MOD_LOAD_POLL,
) -> CheckResult:
    """Definitive proof the mod loads: spawn a game and poll /health for a real GameState.

    Slow — it launches the game — so the command only runs this when `--check-mod-load` is given
    and the cheap binary/mod/display checks have already passed. This spawns the *bare* KTANE
    binary (the mod serves the HTTP endpoints); it does not touch Redis, so Redis being down does
    not gate it.
    """
    manager = GameProcessManager()
    try:
        port = await manager.start()
    except (OSError, RuntimeError) as exc:  # OSError covers Game/ModNotFoundError
        return CheckResult.failed(name, "could not spawn the game", str(exc))

    client = KtaneClient(url=f"http://localhost:{port}")
    try:  # noqa: WPS501  (teardown of the spawned game must always run)
        return await _poll_for_mod(client, name=name, load_timeout=load_timeout, poll=poll)
    finally:
        await _teardown_game(client, manager)


async def _poll_for_mod(
    client: KtaneClient,
    *,
    name: str = MOD_LOAD_CHECK,
    load_timeout: float = MOD_LOAD_TIMEOUT,
    poll: float = MOD_LOAD_POLL,
    hint: str = "Files are present but the mod is not loading.",
) -> CheckResult:
    """Poll the game's /health until a real GameState appears, or time out."""
    with anyio.move_on_after(load_timeout):
        while True:
            try:
                state = await client.get_game_state()
            except (httpx.HTTPError, OSError):
                state = GameState.unknown  # not listening yet — keep polling
            if state is not GameState.unknown:
                return CheckResult.passed(name, f"mod responding (state={state.name})")
            await anyio.sleep(poll)
    return CheckResult.failed(name, f"no /health response within {load_timeout:.0f}s", hint)


async def _teardown_game(client: KtaneClient, manager: GameProcessManager) -> None:
    """Best-effort shutdown of the probe client and spawned game."""
    with contextlib.suppress(Exception):
        await client.stop()
    with contextlib.suppress(Exception):
        await manager.terminate()
