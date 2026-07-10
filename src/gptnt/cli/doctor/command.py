from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

from cyclopts import Parameter
from cyclopts.types import ExistingFile
from rich.console import Console

from gptnt.cli.checks.game import (
    MOD_LOAD_CHECK,
    check_display,
    check_game_binary,
    check_mod_files,
    check_mod_load,
)
from gptnt.cli.checks.machine import check_machine
from gptnt.cli.checks.players import PlayerReport, check_players, check_tokens_per_image
from gptnt.cli.checks.render import render_players, render_report
from gptnt.cli.checks.result import CheckResult
from gptnt.cli.checks.services import check_em_port, check_observability, check_redis
from gptnt.cli.config_discovery import discover_players
from gptnt.cli.doctor.run_plan import RunPlanResult, analyze_run_plan
from gptnt.cli.run.manifest import RunManifest

if TYPE_CHECKING:
    from gptnt.experiments.spec import ExperimentSpec

console = Console()

ManifestArgument = Annotated[
    ExistingFile | None,
    Parameter(help="Optional run.yaml to also cross-check as a run plan (roster + resume state)."),
]
CheckModLoadOption = Annotated[
    bool,
    Parameter(
        name="--check-mod-load",
        help="Spawn a game instance and poll /health to confirm the KTANE mod loads — slow.",
    ),
]
LiveOption = Annotated[
    bool,
    Parameter(
        name="--live", help="Make ONE real request per model (SPENDS MONEY) to test endpoints."
    ),
]


@dataclass(frozen=True)
class DiagnoseResult:
    """The full doctor outcome.

    Whether anything fatal failed, the model matrix, and — in run-plan mode — the run-plan result
    (which carries the generated specs `gptnt run` reuses).
    """

    failed: bool
    player_reports: list[PlayerReport]
    run_plan: RunPlanResult | None


async def doctor(
    manifest: ManifestArgument = None,
    *,
    check_mod_load: CheckModLoadOption = False,
    live: LiveOption = False,
) -> None:
    """Check that this machine is ready to run the benchmark, and print exact fixes for what isn't.

    Pass a `run.yaml` to additionally cross-check its roster against what generation requires (this
    catches a roster player the generated specs never cover before it silently stalls) and report
    resume state.
    """
    run = None
    if manifest is not None:
        run = RunManifest.from_path(manifest)
    diagnosis = await diagnose(run, check_mod_load=check_mod_load, live=live)
    if diagnosis.failed:
        raise RuntimeError("Doctor found problems; fix the rows above.")


async def diagnose(
    run: RunManifest | None,
    *,
    check_mod_load: bool = False,
    live: bool = False,
    specs: list[ExperimentSpec] | None = None,
    include_infra: bool = True,
) -> DiagnoseResult:
    """Run + render the full doctor report against an already-loaded manifest (or None).

    `specs`, when given, is a disk-loaded spec set (the `gptnt run` path). The run-plan cross-check
    reports against it instead of regenerating from the manifest.

    `include_infra=False` skips the redis/game/display/machine checks.
    """
    matrix = await check_players(_doctor_targets(run), live=live)
    render_players(console, matrix.details)
    failed = not matrix.details or any(report.failed for report in matrix.reports)

    system_failed, run_plan_result = await _render_system_checks(
        run,
        matrix.config_to_player,
        tokens_per_image=check_tokens_per_image(matrix.details),
        check_mod_load=check_mod_load,
        specs=specs,
        include_infra=include_infra,
    )
    failed = system_failed or failed

    return DiagnoseResult(failed=failed, player_reports=matrix.reports, run_plan=run_plan_result)


def _doctor_targets(run: RunManifest | None) -> list[tuple[str, str | None]]:
    """The (player, provider) pairs to validate.

    The manifest roster, else every discovered player.
    """
    if run is None:
        return [(name, None) for name in discover_players()]
    return [(entry.player, entry.provider) for entry in run.players]


async def _render_system_checks(
    run: RunManifest | None,
    config_to_player: dict[str, str | None],
    *,
    tokens_per_image: list[CheckResult],
    check_mod_load: bool,
    specs: list[ExperimentSpec] | None = None,
    include_infra: bool = True,
) -> tuple[bool, RunPlanResult | None]:
    """Run + render the image-token/infra/machine/run-plan checks."""
    infra = await _infrastructure_checks(check_mod_load=check_mod_load) if include_infra else []
    machine = check_machine() if include_infra else []
    run_plan_result = None if run is None else _run_plan_checks(run, config_to_player, specs=specs)
    run_plan_findings = [] if run_plan_result is None else run_plan_result.findings

    sections: dict[str, list[CheckResult]] = {}
    # per-player image-token cost, right after the model matrix it stems from
    if tokens_per_image:
        sections["Image tokens"] = tokens_per_image
    if run_plan_findings:  # render the run-plan section right after the model matrix it stems from
        sections["Run plan"] = run_plan_findings
    if infra:
        sections["Infrastructure"] = infra
    if machine:
        sections["Machine"] = machine
    render_report(console, sections)
    failed = any(
        check.status == "fail"
        for check in (*tokens_per_image, *infra, *machine, *run_plan_findings)
    )
    return failed, run_plan_result


def _run_plan_checks(
    run: RunManifest,
    config_to_player: dict[str, str | None],
    *,
    specs: list[ExperimentSpec] | None = None,
) -> RunPlanResult:
    """Run the roster cross-check.

    Isolates a crash so it can never abort the rest of the report.
    """
    try:
        return analyze_run_plan(run, config_to_player, specs=specs)
    except Exception as exc:  # noqa: BLE001 — a crashing cross-check must not abort the report
        return RunPlanResult(
            findings=[CheckResult.failed("Run plan", "cross-check crashed", str(exc)[:200])],
            specs=[],
            config_to_player={},
        )


async def _infrastructure_checks(*, check_mod_load: bool) -> list[CheckResult]:
    """Run the full system-state checks."""
    redis = await check_redis()
    game = check_game_binary()
    mod_files = check_mod_files()
    display = check_display()
    em_port = await check_em_port()
    observability = await check_observability()
    mod_loads = await _mod_load_row(
        enabled=check_mod_load, prerequisites=(game, mod_files, display)
    )

    infra = [redis, game, mod_files, display, em_port, observability, mod_loads]

    return infra


async def _mod_load_row(*, enabled: bool, prerequisites: tuple[CheckResult, ...]) -> CheckResult:
    """The mod-load row: skip (with the flag to run it) when disabled or a prerequisite failed."""
    if not enabled:
        return CheckResult.skipped(MOD_LOAD_CHECK, "not run", "run with --check-mod-load")

    blockers = [check.name for check in prerequisites if check.status == "fail"]
    if blockers:
        return CheckResult.skipped(MOD_LOAD_CHECK, f"skipped because {', '.join(blockers)} failed")
    return await check_mod_load()
