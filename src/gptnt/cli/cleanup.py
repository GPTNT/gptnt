from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress
from rich.table import Table
from wandb.apis.public import Runs

from gptnt.cli._fields import WandbEntityOption, WandbProjectOption
from gptnt.common.logger import create_progress
from gptnt.common.paths import Paths
from gptnt.experiments.wandb import (
    collate_runs_per_experiment_per_game,
    delete_old_experiment_outputs,
    get_runs_from_wandb,
    mark_duplicate_runs_as_old,
    mark_falsely_finished_as_old,
    mark_mismatched_player_games_as_old,
    mark_runs_without_output_files_as_old,
    parse_experiment_outputs_from_directory,
)

console = Console()

paths = Paths()


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


def _get_all_runs(
    *,
    wandb_entity: str,
    wandb_project: str,
    include_dummy_runs: bool = False,
    progress: Progress,
    chunk_size: int = 2000,
) -> Runs:
    """Get all runs from the specified WandB entity and project."""
    task = progress.add_task("Fetching runs from WandB", total=None)
    filters_for_dummies = [
        {"config.defuser_name": {"$nin": ["test-defuser", "test-random", "test-oracle"]}},
        {"config.expert_name": {"$nin": ["test-expert"]}},
    ]
    if include_dummy_runs:
        filters_for_dummies = []
    all_runs = get_runs_from_wandb(
        f"{wandb_entity}/{wandb_project}",
        additional_filters=filters_for_dummies,
        per_page=chunk_size,
    )
    progress.update(task, total=len(all_runs), completed=len(all_runs))
    return all_runs


def cleanup_experiment_outputs(
    directory: Annotated[
        Path | None,
        typer.Argument(
            help="Directory containing experiment JSON files to delete. Without this, we just do things on WandB",
            exists=True,
        ),
    ] = None,
    *,
    wandb_entity: WandbEntityOption,
    wandb_project: WandbProjectOption,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Don't actually change anything.")
    ] = False,
    include_dummy_runs: Annotated[
        bool,
        typer.Option(
            "--include-dummy-runs",
            help="Whether to include dummy runs in the checking, which can be A LOT",
        ),
    ] = False,
) -> None:
    """Consolidate and cleanup experiment outputs and WandB runs in one go."""
    console.rule("[bold]Experiment Cleanup[/bold]")
    _print_run_config(
        dry_run=dry_run, wandb_path=f"{wandb_entity}/{wandb_project}", directory=directory
    )
    with create_progress(extra_fields=["extra"]) as progress:
        all_runs = _get_all_runs(
            wandb_entity=wandb_entity,
            wandb_project=wandb_project,
            include_dummy_runs=include_dummy_runs,
            progress=progress,
        )
        if len(all_runs) == 0:
            console.print("[yellow]No runs found on WandB. Nothing else to do.[/yellow]")
            raise typer.Exit(code=0)

        collated_runs = collate_runs_per_experiment_per_game(all_runs, progress=progress)
        mark_mismatched_player_games_as_old(collated_runs, progress=progress, dry_run=dry_run)
        mark_duplicate_runs_as_old(collated_runs, progress=progress, dry_run=dry_run)
        mark_falsely_finished_as_old(collated_runs, progress=progress, dry_run=dry_run)

        if directory is None:
            console.print("[yellow]No directory provided, so skipping file deletion.[/yellow]")
            raise typer.Exit(code=0)

        # Parse all the outputs from the output dir
        experiment_outputs = parse_experiment_outputs_from_directory(directory, progress=progress)
        if len(experiment_outputs) == 0:
            console.print("[yellow]No experiment output files found. Nothing else to do.[/yellow]")
            raise typer.Exit(code=0)

        # If the run does not have an output file, mark the run as old
        mark_runs_without_output_files_as_old(
            runs=all_runs,
            experiment_outputs=experiment_outputs,
            progress=progress,
            dry_run=dry_run,
        )

        # For all the valid runs, delete any output files that are not in that list and therefore
        # are invalid
        all_runs = _get_all_runs(
            wandb_entity=wandb_entity,
            wandb_project=wandb_project,
            include_dummy_runs=include_dummy_runs,
            progress=progress,
        )
        if len(all_runs) == 0:
            console.print("[yellow]No runs found on WandB. Nothing else to do.[/yellow]")
            raise typer.Exit(code=0)
        collated_runs = collate_runs_per_experiment_per_game(all_runs, progress=progress)

        delete_old_experiment_outputs(
            all_runs, experiment_outputs, progress=progress, dry_run=dry_run
        )

        # Re-parse experiment outputs for final reporting
        experiment_outputs = parse_experiment_outputs_from_directory(directory, progress=progress)

    console.print("[green]Experiment cleanup complete![/green]")
    console.print(f"Runs on WandB: {len(all_runs)}.")
    console.print(f"Collated experiments: {len(collated_runs)}.")
    console.print(f"Experiment outputs found: {len(experiment_outputs)}.")

    console.print("[dim]fin[/dim]")
