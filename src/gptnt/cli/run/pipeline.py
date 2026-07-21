import os
from pathlib import Path
from typing import Literal

import anyio
from rich.console import Console
from rich.table import Table

from gptnt.cli.doctor.command import diagnose
from gptnt.cli.interactive.submit import send_experiments
from gptnt.cli.run.manifest import RunManifest
from gptnt.cli.run.monitor import monitor_interactive, monitor_status, render_stream
from gptnt.common.paths import Paths, remove_empty_experiment_recorder_outputs
from gptnt.experiments.spec import ExperimentSpec, load_specs_from_dir
from gptnt.interactive.orchestration import (
    ProcessOrchestrator,
    handle_signals,
    spawn_experiment_manager,
    spawn_players,
    spawn_rooms,
)
from gptnt.observability.settings import ObservabilitySettings

console = Console()
paths = Paths()


async def run_pipeline(
    manifest: RunManifest,
    *,
    manifest_stem: str,
    force: bool = False,
    live: bool = False,
    interactive: bool = False,
) -> None:
    """Execute a run manifest end-to-end: load specs, gate, spawn, submit (cross-checked), monitor.

    Specs are NOT generated here. They are loaded from `output/experiment_specs/<manifest_stem>/`,
    written earlier by `gptnt generate`.
    """
    # 0. Load the pre-generated specs. Absent/empty → stop before spawning anything.
    specs_dir = Paths().experiment_specs.joinpath(manifest_stem)
    specs = load_specs_from_dir(specs_dir)
    if not specs:
        console.print(
            f"\n[bold red]No experiment specs found at[/bold red] {specs_dir}\n"
            f"Generate them first with: [bold]gptnt generate {manifest_stem}.yaml[/bold]"
        )
        raise RuntimeError(f"no experiment specs found at {specs_dir}; run `gptnt generate` first")
    console.print(f"[green]Loading {len(specs)} spec(s) from[/green] {specs_dir}")

    # 1. Doctor gate (run-plan mode) against the loaded specs: renders the full report and reports
    #    resume state for exactly the specs that will run.
    diagnosis = await diagnose(manifest, live=live, specs=specs)
    if diagnosis.run_plan is None:  # defensive: a manifest always produces a run-plan result
        console.print("[bold red]Internal error: the run-plan check did not execute.[/bold red]")
        raise RuntimeError("the run-plan check did not execute")

    if diagnosis.failed:
        if not force:
            console.print(
                "\n[bold red]Doctor found problems.[/bold red] Fix the ✗ rows above, or re-run "
                "with [bold]--force[/bold] to proceed anyway."
            )
            raise RuntimeError("Doctor found problems; fix the rows above or re-run with --force.")
        console.print("\n[yellow]--force set: proceeding despite the ✗ rows above.[/yellow]")

    # 2. Resume: reuse the specs the gate's resume check already filtered (one completion query for
    #    the whole run). `None` means resume couldn't be determined, so run all. Exit early if
    #    done.
    remaining = diagnosis.run_plan.remaining_specs
    specs_to_run = specs if remaining is None else remaining
    if not specs_to_run:
        console.print(
            f"[green]All {len(specs)} experiment(s) are already complete "
            f"({manifest.source.value}). Nothing to run.[/green]"
        )
        return

    # 3. Roster cross-check (the structural fix; enforced even under --force): every player the
    #    specs reference must be in the spawned roster, else the run would silently stall.
    _assert_roster_covers_specs(specs_to_run, diagnosis.run_plan.config_to_player)

    # 4. Build the spawn environment from the manifest, then spawn → submit → monitor. W&B is not
    #    configured here — the spawned processes inherit the ambient WANDB_* env untouched.
    env_base = {"PYTHONUNBUFFERED": "1"}
    env_base.update(_observability_env(manifest.observability))

    output_dir, logs_dir = _resolve_dirs()
    _print_summary(manifest, specs, specs_to_run, output_dir, logs_dir)

    await _spawn_submit_monitor(
        manifest, specs_to_run, env_base, output_dir, logs_dir, interactive=interactive
    )


def _assert_roster_covers_specs(
    specs: list[ExperimentSpec], config_to_player: dict[str, str]
) -> None:
    """Abort loudly if any player the specs reference is not provided by the spawned roster."""
    provided = set(config_to_player.values())
    required: set[str] = set()
    for spec in specs:
        required.add(spec.defuser_name)
        if spec.expert_name is not None:
            required.add(spec.expert_name)

    missing = sorted(required - provided)
    if missing:
        console.print(
            "[bold red]Roster does not cover the generated specs.[/bold red] These players are "
            f"required but no roster entry provides them: {', '.join(missing)}. This run would "
            "stall forever, so it is aborting before queueing anything."
        )
        raise RuntimeError("roster does not cover the generated specs")


# TODO: This feels stupid?
def _observability_env(level: Literal["full", "limited", "off"]) -> dict[str, str]:
    """Map the manifest's observability level to instrumentation env overrides.

    Both presets are derived from `ObservabilitySettings` so the flag names live in exactly one
    place; `limited` additionally requests aggressive tail-sampling via the OTel resource
    attribute.
    """
    if level == "full":
        return {}
    if level == "off":
        return ObservabilitySettings.off().to_env()

    env = ObservabilitySettings.limited().to_env()
    existing = os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "")
    env["OTEL_RESOURCE_ATTRIBUTES"] = f"{existing},sampling.aggressive=true".strip(",")
    return env


def _resolve_dirs() -> tuple[Path, Path]:
    """Resolve the recorder-output dir (pinned via env, else a fresh timestamp) and a logs dir.

    Computed exactly once here, then pinned into the spawn env (`EXPERIMENT_RECORDER_OUTPUTS`) so
    the recorder subprocesses and the resume check can never disagree about where this run writes.
    """
    output_dir = paths.experiment_outputs
    logs_dir = paths.logs.joinpath(f"run_{output_dir.name}/")
    return output_dir, logs_dir


def _print_summary(
    manifest: RunManifest,
    all_specs: list[ExperimentSpec],
    specs_to_run: list[ExperimentSpec],
    output_dir: Path,
    logs_dir: Path,
) -> None:
    """Print a compact pre-flight summary of what the run will do."""
    total_players = sum(player.count for player in manifest.players)
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(no_wrap=True)
    table.add_column(highlight=True)
    table.add_row("Suites:", ", ".join(manifest.suites))
    table.add_row("Rooms:", str(manifest.rooms))

    if manifest.displays is not None:
        table.add_row("Displays:", ", ".join(f":{display}" for display in manifest.displays))

    for player in manifest.players:
        suffix = f"@{player.provider}" if player.provider else ""
        table.add_row(f"Player ({player.player}{suffix}):", str(player.count))

    table.add_row("Total processes:", str(1 + manifest.rooms + total_players))
    table.add_row("Observability:", manifest.observability)

    already_done = len(all_specs) - len(specs_to_run)
    table.add_row("Specs to run:", f"{len(specs_to_run)} ({already_done} already complete)")
    table.add_section()
    table.add_row("Logs dir:", str(logs_dir))
    table.add_row("Output dir:", str(output_dir))

    console.print()
    console.print(table)
    console.print()


async def _spawn_submit_monitor(
    manifest: RunManifest,
    specs: list[ExperimentSpec],
    env_base: dict[str, str],
    output_dir: Path,
    logs_dir: Path,
    *,
    interactive: bool = False,
) -> None:
    """The orchestration seam: spawn EM/rooms/players, submit in-process, then monitor.

    Interactive mode tees each process's logs to the terminal (docker-compose style) via a task
    group `spawn()` streams into; otherwise a live status table is shown.
    """
    remove_empty_experiment_recorder_outputs(paths.experiment_recorder_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
    output_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240

    orch = ProcessOrchestrator(
        logs_dir=logs_dir, output_dir=output_dir, env_base=env_base, interactive=interactive
    )

    async with handle_signals(orch):
        if interactive:
            async with anyio.create_task_group() as task_group:
                orch.on_spawn = lambda tp: task_group.start_soon(render_stream, tp)
                await _spawn_and_submit(orch, manifest, specs, output_dir)
                await monitor_interactive(orch)
                task_group.cancel_scope.cancel()
        else:
            await _spawn_and_submit(orch, manifest, specs, output_dir)
            await monitor_status(orch)

    console.print()
    console.rule("[bold green]Run finished[/bold green]")
    console.print(f"  Logs saved to:               {logs_dir}")
    console.print(f"  Experiment outputs saved to: {output_dir}")


async def _spawn_and_submit(
    orch: ProcessOrchestrator, manifest: RunManifest, specs: list[ExperimentSpec], output_dir: Path
) -> None:
    """Spawn EM/rooms/players, submit the specs in-process, and tearing down on fail."""
    await spawn_experiment_manager(orch)
    await spawn_rooms(orch, manifest.rooms, manifest.displays)
    await spawn_players(
        orch=orch, players=manifest.players, output_dir=output_dir, source=manifest.source
    )

    console.print(f"\n[bold]Submitting {len(specs)} experiment spec(s) to the EM...[/bold]")
    try:
        await send_experiments(specs)
    except Exception as exc:  # a failed submit must tear down the run, not orphan it
        console.print(
            f"[bold red]Failed to submit specs to the experiment manager:[/bold red] {exc}"
        )
        await orch.terminate_all()
        raise RuntimeError("failed to submit specs to the experiment manager") from exc
    console.print("  Specs submitted.")
