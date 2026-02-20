from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
import wandb
from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from gptnt.cli.models import ExperimentsSource
from gptnt.common.paths import Paths

if TYPE_CHECKING:
    from pydantic import UUID4
    from wandb.apis.public import Run

    from gptnt.experiments.wandb import CollatedRuns

console = Console()
paths = Paths()


# Status constants
STATUS_DONE = "done"
STATUS_RUNNING = "running"
STATUS_FAILED = "failed"
STATUS_NOT_STARTED = "not attempted"

STATUS_ICONS: dict[str, str] = {  # noqa: WPS407
    STATUS_DONE: "✅",
    STATUS_RUNNING: "🔄",
    STATUS_FAILED: "❌",
    STATUS_NOT_STARTED: "·",
}

STATUS_STYLES: dict[str, str] = {  # noqa: WPS407
    STATUS_DONE: "green",
    STATUS_RUNNING: "cyan",
    STATUS_FAILED: "red",
    STATUS_NOT_STARTED: "dim",
}

# CLI type aliases

WandbEntityOption = Annotated[
    str,
    typer.Option(
        "--wandb-entity",
        help="WandB entity (user or team) name",
        envvar="WANDB_ENTITY",
        rich_help_panel="WandB",
    ),
]

WandbProjectOption = Annotated[
    str,
    typer.Option(
        "--wandb-project",
        help="WandB project name",
        envvar="WANDB_PROJECT",
        rich_help_panel="WandB",
    ),
]

ExperimentsArgument = Annotated[
    list[ExperimentsSource] | None,
    typer.Argument(
        help=(
            "Zero or more experiment sources."
            "Pass nothing to generate all; "
            "pass a directory path to load from disk; "
            "pass experiment name(s) (e.g. e1-single-pairwise) to generate only those."
        ),
        parser=ExperimentsSource.from_cli_string,
    ),
]


# Experiment loading
def _generate_experiments_to_tmpdir(tmpdir: Path, names: list[str] | None = None) -> list[str]:
    """Run generate_experiments as a subprocess, directing output to tmpdir."""
    command = [sys.executable, "-m", "gptnt.entrypoints.generate_experiments"]

    if names is None:
        names = sorted(
            path.stem for path in paths.configs.joinpath("experiment").glob("e[1-9]*.yaml")
        )
    for experiment in names:
        console.print(f"  Adding experiment variant: [cyan]{experiment}[/cyan]")
        env = {**os.environ, "EXPERIMENTS": str(tmpdir)}
        proc = subprocess.run(  # noqa: S603
            [*command, f"experiment={experiment}"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            console.print("[red]generate_experiments failed:[/red]")
            console.print(proc.stderr)
            raise typer.Exit(code=1)

    return _load_experiment_names_from_dir(tmpdir)


def _load_experiment_names_from_dir(directory: Path) -> list[str]:
    """Load experiment names from a directory of JSON files."""
    experiment_names = [path.stem for path in directory.glob("*.json")]
    return experiment_names


def _resolve_experiments(sources: list[ExperimentsSource]) -> list[str]:
    """Load or generate experiments based on parsed CLI sources."""
    if not sources:
        console.print("[dim]Generating all experiments via entrypoint...[/dim]")
        with tempfile.TemporaryDirectory() as tmpdir:
            return _generate_experiments_to_tmpdir(Path(tmpdir))

    if sources[0].kind == "dir":
        if len(sources) > 1:
            raise typer.BadParameter("Cannot mix a directory path with experiment names.")
        directory = Path(sources[0].raw)
        console.print(f"[dim]Loading experiments from {directory}[/dim]")
        return _load_experiment_names_from_dir(directory)

    if any(src.kind == "dir" for src in sources):
        raise typer.BadParameter("Cannot mix a directory path with experiment names.")

    names = [src.raw for src in sources]
    console.print(f"[dim]Generating experiments for: {', '.join(names)}[/dim]")
    with tempfile.TemporaryDirectory() as tmpdir:
        return _generate_experiments_to_tmpdir(Path(tmpdir), names=names)


# ---------------------------------------------------------------------------
# Wandb helpers
# ---------------------------------------------------------------------------


def _is_run_valid(run: Run) -> bool:
    """Return True if a run finished cleanly with no hard crash."""
    return (
        "is_hard_crash" in run.summary
        and run.summary.get("is_hard_crash", True) is False
        and run.state == "finished"
    )


def _fetch_all_runs(wandb_path: str, experiment_names: list[str]) -> CollatedRuns:
    """Fetch ALL runs from wandb with no state/tag filters and collate them."""
    with console.status(f"Fetching all runs from [cyan]{wandb_path}[/cyan]..."):
        api = wandb.Api()
        runs = api.runs(
            wandb_path,
            filters={
                "$and": [{"$or": [{"config.experiment_name": name} for name in experiment_names]}]
            },
        )
    console.print(f"  Fetched [bold]{len(runs)}[/bold] total runs from wandb.")

    # Group runs by experiment_name -> session_id -> [runs].
    collated: CollatedRuns = defaultdict(lambda: defaultdict(list))
    for run in runs:
        exp_name: str = run.config["experiment_name"]
        session_id: UUID4 = run.config["session_id"]
        collated[exp_name][session_id].append(run)

    return collated


# Status helpers
def _session_status(session_runs: list[Run]) -> str:
    """Determine the aggregate status for a single session."""
    tags_all = [tag for run in session_runs for tag in (run.tags or [])]
    if "old" in tags_all:
        return STATUS_FAILED
    states = {run.state for run in session_runs}
    if states & {"running", "pending"}:
        return STATUS_RUNNING
    if states == {"finished"} and all(_is_run_valid(run) for run in session_runs):
        return STATUS_DONE
    return STATUS_FAILED


def _experiment_summary(session_statuses: dict[UUID4, str]) -> tuple[str, str, str]:
    """Return (overall_status, sessions_str, notes_str) for an experiment."""
    counts: dict[str, int] = defaultdict(int)
    for st in session_statuses.values():
        counts[st] += 1

    done_n = counts[STATUS_DONE]
    running_n = counts[STATUS_RUNNING]
    failed_n = counts[STATUS_FAILED]
    total = len(session_statuses)

    if done_n:
        overall = STATUS_DONE
    elif running_n:
        overall = STATUS_RUNNING
    else:
        overall = STATUS_FAILED

    notes = ", ".join(filter(None, [f"{failed_n} failed" if failed_n else ""]))
    return overall, f"{done_n}/{total}", notes


# Rendering
def _render_table(expected_names: list[str], collated: CollatedRuns) -> None:  # noqa: WPS210
    table = Table(
        box=box.SIMPLE,
        show_header=True,
        show_footer=True,
        show_edge=False,
        pad_edge=False,
        highlight=False,
        expand=False,
    )
    table.add_column("#", justify="right", no_wrap=True)
    table.add_column("Experiment", style="default", no_wrap=True)
    table.add_column("St", justify="center", no_wrap=True)
    table.add_column("✅/n", justify="right", no_wrap=True)
    table.add_column("Notes", style="dim", no_wrap=True)

    summary: dict[str, int] = defaultdict(int)

    for idx, name in enumerate(expected_names):
        sessions = collated.get(name, {})
        status, notes_str = STATUS_NOT_STARTED, ""
        sessions_str = ""
        # if we have, update it
        if sessions:
            session_statuses = {sid: _session_status(runs) for sid, runs in sessions.items()}
            status, sessions_str, notes_str = _experiment_summary(session_statuses)

        summary[status] += 1
        icon, style = STATUS_ICONS[status], STATUS_STYLES[status]
        effective_style = "dim" if status == STATUS_NOT_STARTED else style

        count_text = Text(sessions_str, style=effective_style, justify="right")

        table.add_row(
            str(idx),
            Text(name, style=effective_style),
            Text(icon, justify="center"),
            count_text,
            Text(notes_str, style="dim"),
        )

    console.print(table)
    _render_summary(summary, total=len(expected_names))


def _render_summary(summary: dict[str, int], total: int) -> None:
    line = Text("  ")
    first = True
    for status in (STATUS_DONE, STATUS_RUNNING, STATUS_FAILED, STATUS_NOT_STARTED):
        count = summary.get(status, 0)
        if not count:
            continue
        if not first:
            _ = line.append("    ", style="dim")
        _ = line.append(f"{STATUS_ICONS[status]} {count} {status}", style=STATUS_STYLES[status])
        first = False
    remaining = summary.get(STATUS_FAILED, 0) + summary.get(STATUS_NOT_STARTED, 0)
    _ = line.append(f"  ({remaining} remaining / {total} total)", style="dim")
    console.print(line)
    console.print()


def check_experiments(
    sources: ExperimentsArgument = None,
    *,
    wandb_entity: WandbEntityOption,
    wandb_project: WandbProjectOption,
) -> None:
    """Check which experiments exist on wandb and their current status."""
    sources = sources or []
    console.print()

    expected = _resolve_experiments(sources)
    if not expected:
        console.print("[red]No experiments found. Aborting.[/red]")
        raise typer.Exit(code=1)

    console.print(f"  Loaded [bold]{len(expected)}[/bold] expected experiments.\n")

    wandb_path = f"{wandb_entity}/{wandb_project}"
    console.print(f"[bold]Checking experiments against[/bold] [cyan]{wandb_path}[/cyan]\n")
    collated_runs = _fetch_all_runs(wandb_path, expected)

    expected_names = sorted(expected)
    console.print()
    _render_table(expected_names, collated_runs)
