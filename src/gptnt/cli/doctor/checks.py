"""The individual `gptnt doctor` checks.

Each check is a small function that returns one :class:`CheckResult` (or a small list of them) and
**never raises**: a check should report failure rather than aborting the whole report. The command
layer (`command.py`) decides which checks to run for each mode and renders the results
(`render.py`). This module owns only "what does each check verify and how do I fix it".

Heavy dependencies (hydra via `model_validation`, `coredis`, the game spawn machinery) are imported
at module top: cyclopts lazy-loads command modules, so this module only loads when a doctor command
actually runs.

Secret safety: the model checks may surface pydantic-ai's own "set the X environment variable" text
(which names a var), but no environment variable VALUE is ever read, printed, or logged.
"""

from __future__ import annotations

import contextlib
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlsplit

import anyio
import httpx
import psutil

from gptnt.cli.doctor.validation import (
    ModelValidationResult,
    live_check_model_config,
    validate_model_config,
)
from gptnt.common.paths import Paths
from gptnt.common.runtime_settings import RuntimeSettings
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.executable import (
    GameNotFoundError,
    ModNotFoundError,
    ensure_mod_exists,
    get_executable_path,
)
from gptnt.ktane.process_manager import GameProcessManager
from gptnt.ktane.state.game import GameState
from gptnt.observability.settings import ObservabilitySettings

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gptnt.cli.doctor.validation import LiveCheckResult

CheckStatus = Literal["pass", "fail", "warn", "skip"]
"""How a check landed: `pass` ✓, `fail` ✗ (fails the run), `warn` ⚠ (reported, never fails), `skip`
⊘ (not applicable here, e.g. an X display on macOS)."""

paths = Paths()

# The infra endpoints doctor probes all come from their single shared sources: the Redis DSN and EM
# endpoint from `core.runtime_settings.RuntimeSettings`, the OTLP endpoint from
# `core.observability.settings.ObservabilitySettings` — the same sources the runtime
# binds, so doctor can't report against a different endpoint than the one the services use.

_NET_TIMEOUT = 3.0
DISK_WARN_GIB = 10.0
MOD_LOAD_TIMEOUT = 45.0
MOD_LOAD_POLL = 1.0

# Hints offer Docker as one easy option, not a mandate — point REDIS_DSN /
# OTEL_EXPORTER_OTLP_ENDPOINT at your own services instead if you prefer.
REDIS_HINT = "Run a Redis here — e.g. `docker compose up -d`, or set REDIS_DSN to your own."
OTEL_HINT = "Optional — run a collector here (e.g. `docker compose up -d`) or set OTEL_EXPORTER_OTLP_ENDPOINT."
# "Reachable" means a real service *answered*, not that a port accepted a TCP handshake: a
# container runtime's port-forward with nothing behind it accepts the connect, then drops it
# (an anyio stream error / RemoteProtocolError). Refused/timed-out connects raise
# OSError/TimeoutError.
_REDIS_PROBE_ERRORS = (OSError, TimeoutError, anyio.EndOfStream, anyio.BrokenResourceError)


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one doctor check.

    `detail` is what was found (shown always). `hint` is the fix and is shown on ✗/⚠.
    """

    name: str
    status: CheckStatus
    detail: str = ""
    hint: str = ""


@dataclass(frozen=True)
class PlayerReport:
    """One model across three independent boxes: exists → instantiates → live.

    The boxes are hierarchical (a box can't pass if its predecessor failed), so a failed box leaves
    the downstream ones as `skip`.
    """

    label: str

    exists: CheckStatus
    """The config is found and the YAML composes."""

    instantiates: CheckStatus
    """It builds into a working `pydantic_ai.Agent`.

    ⚠ when valid but the provider credential is unset.
    """

    live: CheckStatus
    """A real request answered (only run under `--live`; `skip` otherwise)."""

    note: str = ""

    @property
    def failed(self) -> bool:
        """True if any box that actually ran failed (`warn`/`skip` never fail the run)."""
        return "fail" in {self.exists, self.instantiates, self.live}


def _nearest_existing(path: Path) -> Path:
    """Walk up to the first existing ancestor (the output dir may not exist yet)."""
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return Path(path.anchor or ".")


async def _redis_pings(host: str, port: int) -> bool:
    """True iff a Redis answers its native PING health check (+PONG) at host:port.

    A port that merely accepts the TCP connection (e.g. a container runtime's port-forward with
    nothing behind it) is not a running Redis.
    """
    try:
        with anyio.fail_after(_NET_TIMEOUT):
            stream = await anyio.connect_tcp(host, port)
            async with stream:
                await stream.send(b"PING\r\n")
                reply = await stream.receive()
    except _REDIS_PROBE_ERRORS:
        return False
    return reply.startswith(b"+PONG")


async def _http_responds(url: str) -> bool:
    """True iff an HTTP server answers at `url` with any status (not a dead port-forward)."""
    try:
        async with httpx.AsyncClient(timeout=_NET_TIMEOUT) as client:
            _ = await client.get(url)
    except httpx.HTTPError:
        return False
    return True


# --- Models ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PlayerDetail:
    """One model's full validation result: the ✓/✗ boxes plus the underlying data.

    `static` carries every resolved field so the detailed rows can be rendered; `live` is the real-
    request result when `--live` ran, else `None`; `report` keeps the matrix-compatible boxes that
    drive the failed/exit decision.
    """

    report: PlayerReport
    static: ModelValidationResult
    live: LiveCheckResult | None = None


@dataclass(frozen=True)
class PlayerMatrix:
    """Every model's detail plus the config-name → player_name mapping.

    The mapping comes from the SAME `validate_model_config` pass that builds the detail, so the
    report the user sees and the roster resolution the run-plan cross-check uses can never disagree
    (CLAUDE.md §3). Keyed by the *config* name; a value is `None` when the config did not
    instantiate far enough to yield a `capabilities.player_name`.
    """

    details: list[PlayerDetail]
    config_to_player: dict[str, str | None]

    @property
    def reports(self) -> list[PlayerReport]:
        """The matrix-compatible ✓/✗ boxes, one per model."""
        return [detail.report for detail in self.details]


async def check_players(targets: Sequence[tuple[str, str | None]], *, live: bool) -> PlayerMatrix:
    """Validate each model into its full detail (boxes + every resolved field + optional live).

    Also returns a `config name → player_name` mapping derived from the same validation, so the
    run-plan cross-check can resolve roster configs without composing twice. Empty `targets` yields
    empty `details` (the caller renders the "no configs" message and fails).

    Runs sequentially on purpose: `validate_model_config` clears the global Hydra singleton on
    every call, so concurrent composition would race.
    """
    details: list[PlayerDetail] = []
    config_to_player: dict[str, str | None] = {}
    for model_name, provider in targets:
        label = model_name if provider is None else f"{model_name}@{provider}"
        try:
            # Sequential await is required: validate_model_config clears the global Hydra
            # singleton on each call, so models cannot be composed concurrently.
            detail = await _player_detail(label, model_name, provider, live=live)  # noqa: WPS476
        except Exception as exc:  # noqa: BLE001 — isolate one bad config from the rest of the run
            crashed = ModelValidationResult(model_name, provider, ok=False, error=str(exc))
            detail = PlayerDetail(
                PlayerReport(label, "fail", "skip", "skip", f"check crashed: {exc}"), crashed
            )
        details.append(detail)
        capabilities = detail.static.capabilities
        config_to_player[model_name] = capabilities.player_name if capabilities else None
    return PlayerMatrix(details, config_to_player)


async def _player_detail(
    label: str, model_name: str, provider: str | None, *, live: bool
) -> PlayerDetail:
    """Validate one model into its full detail (boxes + resolved fields + optional live result)."""
    static = validate_model_config(model_name, provider)
    exists, instantiates, note = _static_boxes(static)
    # Live only runs when requested AND the model instantiated with its credential present (a ⚠
    # instantiate means the key is unset, so there is nothing to call).
    if not (live and exists == "pass" and instantiates == "pass"):
        return PlayerDetail(PlayerReport(label, exists, instantiates, "skip", note), static)

    outcome = await live_check_model_config(model_name, provider)
    if outcome.ok:
        report = PlayerReport(
            label, exists, instantiates, "pass", f"answered in {outcome.latency_seconds:.2f}s"
        )
    else:
        report = PlayerReport(label, exists, instantiates, "fail", outcome.error or "")
    return PlayerDetail(report, static, outcome)


def _static_boxes(outcome: ModelValidationResult) -> tuple[CheckStatus, CheckStatus, str]:
    """Map a static validation outcome to (exists, instantiates, note).

    Instantiation IS the credential check: an unset provider key is a ⚠ carrying pydantic-ai's own
    "set the X environment variable" text — no hardcoded key map to maintain.
    """
    if outcome.error_stage == "compose":  # YAML missing / invalid — nothing to instantiate
        return "fail", "skip", outcome.error or ""
    if not outcome.ok:  # composed, but capabilities/agent failed to build
        return "pass", "fail", outcome.error or ""
    if outcome.missing_credential:
        return "pass", "warn", outcome.error or ""
    return "pass", "pass", f"resolves to {outcome.resolved_model_name or 'instantiated'}"


# --- Infrastructure (full mode only) ----------------------------------------------------------


async def check_redis() -> CheckResult:
    """Is a Redis actually answering at the configured DSN (via PING, not a bare port check)?"""
    parsed = urlsplit(str(RuntimeSettings().redis_dsn))
    host, port = parsed.hostname or "localhost", parsed.port or 6379
    if await _redis_pings(host, port):
        return CheckResult("Redis", "pass", f"reachable at {host}:{port}")
    return CheckResult("Redis", "fail", f"not reachable at {host}:{port}", REDIS_HINT)


def _game_layout_hint() -> str:
    return (
        f"Copy the KTANE build into {paths.ktane} "
        "(Linux: *.x86_64 + ktane_Data/; macOS: *.app; Windows: *.exe + ktane_Data/)."
    )


def check_game_binary() -> CheckResult:
    """Resolve the per-OS game executable under `paths.ktane`."""
    name = "Game binary"
    try:
        executable = get_executable_path()
    except (GameNotFoundError, RuntimeError) as exc:  # RuntimeError == unsupported OS
        return CheckResult(name, "fail", str(exc), _game_layout_hint())
    return CheckResult(name, "pass", str(executable))


def check_mod_files() -> CheckResult:
    """Cheap on-disk check that the 'Gptnt Plays' mod directory exists."""
    name = "Mod files"
    try:
        _ = ensure_mod_exists()
    except ModNotFoundError as exc:
        hint = f"Install the 'Gptnt Plays' mod under {paths.ktane / 'mods'}."
        return CheckResult(name, "fail", str(exc), hint)
    return CheckResult(name, "pass", "'Gptnt Plays' present")


def check_display() -> CheckResult:
    """On Linux, confirm an X display is available; elsewhere it is not required."""
    name = "Display (X)"
    startx_hint = "Start a GPU-backed X server: uv run python scripts/startx.py"
    if sys.platform != "linux":
        return CheckResult(name, "skip", f"not required on {platform.system()}")

    display = os.environ.get("DISPLAY", "")
    if not display:
        return CheckResult(name, "fail", "$DISPLAY is not set", startx_hint)

    display_num = display.rsplit(":", 1)[-1].split(".")[0]
    socket_path = Path(f"/tmp/.X11-unix/X{display_num}")  # noqa: S108  (standard X socket location)
    if socket_path.exists():
        return CheckResult(name, "pass", f"using existing $DISPLAY={display}")
    return CheckResult(
        name,
        "warn",
        f"$DISPLAY={display} set but {socket_path} not found",
        f"If this is a remote/TCP display it may still work; otherwise: {startx_hint}",
    )


async def check_em_port() -> CheckResult:
    """Port :8085 is free (the EM can start) or already serving a healthy EM."""
    runtime = RuntimeSettings()
    name = f"EM port :{runtime.em_port}"
    url = runtime.em_health_url
    kill_hint = "A stale process is squatting the port — clear it with: gptnt kill"
    try:
        async with httpx.AsyncClient(timeout=_NET_TIMEOUT) as client:
            response = await client.get(url)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        # refused/timed-out/filtered connect == Nothing healthy is running here, so the EM can
        return CheckResult(name, "pass", "free (the EM can start here)")
    except httpx.HTTPError as exc:
        # connected, but mid-request timeout or not speaking HTTP
        return CheckResult(name, "fail", f"occupied, not responding: {exc}", kill_hint)
    if response.status_code == httpx.codes.OK:  # pyright: ignore[reportUnnecessaryComparison]
        return CheckResult(name, "pass", "an EM is already running and healthy")

    return CheckResult(name, "fail", f"occupied (HTTP {response.status_code})", kill_hint)


def _otel_host_port() -> tuple[str, int]:
    """Host/port the OTLP collector is expected at.

    Read from OTEL_EXPORTER_OTLP_ENDPOINT (else the default).
    """
    endpoint = ObservabilitySettings().otel_endpoint or "http://localhost:4318/"
    parsed = urlsplit(endpoint)
    return parsed.hostname or "localhost", parsed.port or 4318


async def check_observability() -> CheckResult:
    """Is an OTLP collector reachable? Recommended, not required — a warning, never a failure.

    We only care that the endpoint is up; how it's hosted (Docker, a local collector, a remote
    backend via OTEL_EXPORTER_OTLP_ENDPOINT) is the user's choice.
    """
    host, port = _otel_host_port()
    name = f"otel-collector :{port}"
    if await _http_responds(f"http://{host}:{port}/"):
        return CheckResult(name, "pass", f"reachable at {host}:{port}")
    return CheckResult(name, "warn", f"not reachable at {host}:{port}", OTEL_HINT)


def _detect_gpu() -> str | None:
    """First GPU name via `nvidia-smi` (Linux), or None when unavailable."""
    if sys.platform != "linux":
        return None
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    first_line = completed.stdout.strip().splitlines()
    return first_line[0].strip() if first_line else None


def check_machine() -> list[CheckResult]:
    """Report host specs + free disk; degrade to a single warn if probing the host fails."""
    try:
        return _collect_machine()
    except Exception as exc:  # noqa: BLE001 — purely informational; never abort the report
        return [CheckResult("Machine", "warn", "could not read host info", str(exc))]


def _collect_machine() -> list[CheckResult]:
    """Report host specs (informational) and warn on low free disk for experiment outputs."""
    ram_gib = psutil.virtual_memory().total / 1024**3
    cpus = os.cpu_count() or 0
    spec = f"{platform.system()} {platform.machine()}, {cpus} CPUs, {ram_gib:.1f} GiB RAM"
    gpu = _detect_gpu()
    if gpu:
        spec = f"{spec}, GPU: {gpu}"
    findings = [CheckResult("Machine", "pass", spec)]

    target = _nearest_existing(paths.experiment_recorder_dir)
    free_gib = shutil.disk_usage(target).free / 1024**3
    detail = f"{free_gib:.1f} GiB free on {target}"
    if free_gib < DISK_WARN_GIB:
        findings.append(
            CheckResult(
                "Disk space",
                "warn",
                detail,
                f"Below {DISK_WARN_GIB:.0f} GiB free; experiment recordings accumulate here.",
            )
        )
    else:
        findings.append(CheckResult("Disk space", "pass", detail))
    return findings


MOD_LOAD_CHECK = "Mod loads (game spawn)"


async def check_mod_load() -> CheckResult:
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
        return CheckResult(MOD_LOAD_CHECK, "fail", "could not spawn the game", str(exc))

    client = KtaneClient(url=f"http://localhost:{port}")
    try:  # noqa: WPS501  (teardown of the spawned game must always run)
        return await _poll_for_mod(client)
    finally:
        await _teardown_game(client, manager)


async def _poll_for_mod(client: KtaneClient) -> CheckResult:
    """Poll the game's /health until a real GameState appears, or time out."""
    with anyio.move_on_after(MOD_LOAD_TIMEOUT):
        while True:
            try:
                state = await client.get_game_state()
            except (httpx.HTTPError, OSError):
                state = GameState.unknown  # not listening yet — keep polling
            if state is not GameState.unknown:
                return CheckResult(MOD_LOAD_CHECK, "pass", f"mod responding (state={state.name})")
            await anyio.sleep(MOD_LOAD_POLL)
    return CheckResult(
        MOD_LOAD_CHECK,
        "fail",
        f"no /health response within {MOD_LOAD_TIMEOUT:.0f}s",
        "Files are present but the mod is not loading.",
    )


async def _teardown_game(client: KtaneClient, manager: GameProcessManager) -> None:
    """Best-effort shutdown of the probe client and spawned game."""
    with contextlib.suppress(Exception):
        await client.stop()
    with contextlib.suppress(Exception):
        await manager.terminate()
