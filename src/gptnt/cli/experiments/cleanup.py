from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from cyclopts import Parameter
from cyclopts.types import ExistingDirectory
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress
from rich.table import Table

from gptnt.cli.experiments.models import SourceOption
from gptnt.common.logger import create_progress
from gptnt.common.paths import Paths, remove_empty_experiment_recorder_outputs
from gptnt.experiments.db._extract import compute_experiment_validity, group_by_unique_experiment
from gptnt.experiments.ledger import Source

if TYPE_CHECKING:
    from wandb.apis.public import Runs  # type annotation only; needs the wandb extra at runtime

console = Console()
paths = Paths()


class _NothingToDo(Exception):  # noqa: N818 — internal control-flow signal, not an error
    """Raised by a wandb helper to stop the command on a clean 'nothing to do' path."""


def cleanup_experiment_outputs(
    directory: Annotated[
        ExistingDirectory | None,
        Parameter(
            help="Directory of experiment outputs to clean. Defaults to the recorder output dir."
        ),
    ] = None,
    *,
    source: SourceOption = Source.local,
    dry_run: Annotated[
        bool, Parameter(name="--dry-run", help="Don't actually change anything.")
    ] = False,
    include_dummy_runs: Annotated[
        bool,
        Parameter(name="--include-dummy-runs", help="[wandb] Include dummy runs in the checking."),
    ] = False,
    do_not_old_if_no_output_file: Annotated[
        bool,
        Parameter(
            name="--do-not-old-if-no-output-file",
            help="[wandb] Don't mark a run as old just because it has no output file.",
        ),
    ] = False,
) -> None:
    """Consolidate and clean up experiment outputs (and, with --source wandb, W&B runs)."""
    target = directory or paths.experiment_recorder_dir
    if source is Source.local:
        _cleanup_local_outputs(target, dry_run=dry_run)
        return

    _cleanup_against_wandb(
        directory,
        dry_run=dry_run,
        include_dummy_runs=include_dummy_runs,
        do_not_old_if_no_output_file=do_not_old_if_no_output_file,
    )


def _cleanup_local_outputs(directory: Path, *, dry_run: bool) -> None:
    """Delete output files for experiments that crashed or never reached a valid ending.

    Disk-only and always available: groups `experiment-*.parquet` files by experiment, dropping any
    group that is not a valid, completed experiment (the same validity the DB ingestion stamps).
    """
    console.rule("[bold]Local Experiment Cleanup[/bold]")
    files = list(directory.rglob("experiment-*.parquet"))
    if not files:
        console.print("[yellow]No experiment output files found. Nothing to do.[/yellow]")
        return

    grouped = group_by_unique_experiment(files)
    to_delete = [
        path
        for group_paths in grouped.values()
        if not compute_experiment_validity(group_paths)
        for path in group_paths
    ]

    for path in to_delete:
        if dry_run:
            console.print(f"[dim][To Delete] {path}[/dim]")
        else:
            path.unlink(missing_ok=True)

    if not dry_run:
        remove_empty_experiment_recorder_outputs(directory)

    kept = len(files) - len(to_delete)
    verb = "Would delete" if dry_run else "Deleted"
    console.print(
        f"[green]{len(grouped)} experiment(s) scanned; "
        f"keeping {kept} file(s), {verb.lower()} {len(to_delete)}.[/green]"
    )


def _cleanup_against_wandb(  # noqa: WPS210
    directory: Path | None,
    *,
    dry_run: bool,
    include_dummy_runs: bool,
    do_not_old_if_no_output_file: bool,
) -> None:
    """Mark invalid W&B runs as old and delete local files lacking a valid run (opt-in)."""
    # Imported here, not at module top, so `--source local` works without the wandb extra.
    from gptnt.experiments.ledger.wandb import resolve_wandb_path  # noqa: PLC0415

    wandb_path = resolve_wandb_path()
    console.rule("[bold]Experiment Cleanup (wandb)[/bold]")
    _print_run_config(dry_run=dry_run, wandb_path=wandb_path, directory=directory)

    with create_progress(extra_fields=["extra"]) as progress:
        try:
            _run_wandb_cleanup(
                directory=directory,
                wandb_path=wandb_path,
                dry_run=dry_run,
                include_dummy_runs=include_dummy_runs,
                do_not_old_if_no_output_file=do_not_old_if_no_output_file,
                progress=progress,
            )
        except _NothingToDo:
            return

    console.print("[green]Experiment cleanup complete![/green]")


def _run_wandb_cleanup(  # noqa: WPS210
    *,
    directory: Path | None,
    wandb_path: str,
    dry_run: bool,
    include_dummy_runs: bool,
    do_not_old_if_no_output_file: bool,
    progress: Progress,
) -> None:
    """Run the wandb cleanup steps; raises `_NothingToDo` on a clean early exit."""
    # Imported here, not at module top, so `--source local` works without the wandb extra.
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

    if not do_not_old_if_no_output_file:
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
    # Imported here, not at module top, so `--source local` works without the wandb extra.
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
