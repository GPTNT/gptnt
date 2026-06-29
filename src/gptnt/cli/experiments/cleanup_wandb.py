from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from cyclopts import Parameter
from cyclopts.types import ExistingDirectory
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress
from rich.table import Table

from gptnt.common.logger import create_progress

if TYPE_CHECKING:
    from wandb.apis.public import Runs  # type annotation only; needs the wandb extra at runtime

console = Console()


class _NothingToDo(Exception):  # noqa: N818 — internal control-flow signal, not an error
    """Raised by a wandb helper to stop the command on a clean 'nothing to do' path."""


def reconcile_wandb_runs(
    directory: Annotated[
        ExistingDirectory | None,
        Parameter(
            help="Directory of local experiment outputs to reconcile against W&B. "
            "Omit to only tag remote runs without deleting any local files."
        ),
    ] = None,
    *,
    execute: Annotated[
        bool,
        Parameter(
            name="--execute",
            help="Actually mutate remote W&B state and delete local files. "
            "Without it the command only previews.",
        ),
    ] = False,
    include_dummy_runs: Annotated[
        bool, Parameter(name="--include-dummy-runs", help="Include dummy runs in the checking.")
    ] = False,
    mark_missing_output_as_old: Annotated[
        bool,
        Parameter(
            name="--mark-missing-output-as-old",
            help="Tag a remote run `old` when no local output file matches it.",
            negative="--no-mark-missing-output-as-old",
        ),
    ] = True,
) -> None:
    """Reconcile local outputs against W&B, tagging invalid runs and deleting orphaned files.

    Tags invalid/duplicate/orphaned **remote** W&B runs as `old` and deletes local files lacking a
    valid run. This **mutates remote W&B state**. Previews by default; pass `--execute` to apply.
    """
    # Imported here, not at module top, so the local commands work without the wandb extra.
    from gptnt.experiments.ledger.wandb import resolve_wandb_path  # noqa: PLC0415

    dry_run = not execute
    wandb_path = resolve_wandb_path()
    console.rule("[bold]Reconcile W&B Runs[/bold]")
    _print_run_config(dry_run=dry_run, wandb_path=wandb_path, directory=directory)

    with create_progress(extra_fields=["extra"]) as progress:
        try:
            _run_wandb_cleanup(
                directory=directory,
                wandb_path=wandb_path,
                dry_run=dry_run,
                include_dummy_runs=include_dummy_runs,
                mark_missing_output_as_old=mark_missing_output_as_old,
                progress=progress,
            )
        except _NothingToDo:
            return

    console.print("[green]W&B reconcile complete![/green]")


def _run_wandb_cleanup(  # noqa: WPS210
    *,
    directory: Path | None,
    wandb_path: str,
    dry_run: bool,
    include_dummy_runs: bool,
    mark_missing_output_as_old: bool,
    progress: Progress,
) -> None:
    """Run the wandb cleanup steps; raises `_NothingToDo` on a clean early exit."""
    # Imported here, not at module top, so the local commands work without the wandb extra.
    from gptnt.experiments.wandb_runs import (  # noqa: PLC0415
        cleanup_wandb_runs,
        collate_runs_per_experiment_per_game,
        delete_old_experiment_outputs,
        mark_runs_without_output_files_as_old,
        parse_experiment_outputs_from_directory,
    )

    all_runs = _require_runs(
        wandb_path=wandb_path, include_dummy_runs=include_dummy_runs, progress=progress
    )
    collated_runs = collate_runs_per_experiment_per_game(all_runs, progress=progress)
    cleanup_wandb_runs(collated_runs, progress=progress, dry_run=dry_run)

    if directory is None:
        console.print("[yellow]No directory provided, so skipping file deletion.[/yellow]")
        return

    experiment_outputs = parse_experiment_outputs_from_directory(directory, progress=progress)
    if len(experiment_outputs) == 0:
        console.print("[yellow]No experiment output files found. Nothing else to do.[/yellow]")
        return

    if mark_missing_output_as_old:
        mark_runs_without_output_files_as_old(
            runs=all_runs,
            experiment_outputs=experiment_outputs,
            progress=progress,
            dry_run=dry_run,
        )

    all_runs = _require_runs(
        wandb_path=wandb_path, include_dummy_runs=include_dummy_runs, progress=progress
    )
    delete_old_experiment_outputs(all_runs, experiment_outputs, progress=progress, dry_run=dry_run)


def _print_run_config(*, dry_run: bool, wandb_path: str, directory: Path | None) -> None:
    table = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
    table.add_column("Setting", min_width=14)
    table.add_column("Value")
    table.add_row(
        "Dry Run?", "[b yellow]Yes — nothing will be changed[/b yellow]" if dry_run else "No"
    )
    table.add_row("WandB Path", f"{wandb_path}")
    if directory is None:
        dir_value = "[yellow]N/A - skipping output file deletion[/yellow]"
    else:
        dir_value = f"[green]{directory}[/green] [dim](will scan and delete matching files)[/dim]"
    table.add_row("Output Directory", dir_value)
    console.print(Panel.fit(table, title="[bold]Run Config[/bold]", border_style="blue"))


def _require_runs(*, wandb_path: str, include_dummy_runs: bool, progress: Progress) -> "Runs":
    """Fetch all WandB runs, exiting cleanly when none are found."""
    # Imported here, not at module top, so the local commands work without the wandb extra.
    from gptnt.experiments.wandb_runs import get_runs_from_wandb  # noqa: PLC0415

    task = progress.add_task("Fetching runs from WandB", total=None)
    filters_for_dummies = (
        []
        if include_dummy_runs
        else [
            {"config.defuser_name": {"$nin": ["test-defuser", "test-random", "test-oracle"]}},
            {"config.expert_name": {"$nin": ["test-expert"]}},
        ]
    )
    all_runs = get_runs_from_wandb(
        wandb_path, additional_filters=filters_for_dummies, per_page=2000
    )
    progress.update(task, total=len(all_runs), completed=len(all_runs))
    if len(all_runs) == 0:
        console.print("[yellow]No runs found on WandB. Nothing else to do.[/yellow]")
        raise _NothingToDo
    return all_runs
