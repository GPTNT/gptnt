from pathlib import Path
from typing import Annotated

import structlog
import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from sqlmodel import Session, SQLModel, select

from gptnt.app.experiment_loader.db_connection import get_engine
from gptnt.app.experiment_loader.scanner import ScannedExperiment, scan_experiments_from_directory
from gptnt.common.logger import create_progress
from gptnt.common.paths import Paths
from gptnt.experiments.wandb import (
    collate_runs_per_experiment_per_game,
    get_invalid_runs_from_collated_runs,
    get_runs_from_wandb,
)

logger = structlog.get_logger()
console = Console()

paths = Paths()


db_app = typer.Typer(
    name="db", help="Manage the local DuckDB experiment database.", no_args_is_help=True
)


def _scan_for_experiments(directory: Path, max_workers: int) -> list[ScannedExperiment]:
    with create_progress() as progress:
        scan_task = progress.add_task("Scanning for experiment files", total=None)

        def _on_progress(done: int, total: int) -> None:  # noqa: WPS430
            progress.update(scan_task, total=total, completed=done)

        scanned_experiments, unparsable = scan_experiments_from_directory(
            directory, on_progress=_on_progress, max_workers=max_workers
        )

    if unparsable:
        console.print(
            f"[yellow]\u26a0[/yellow]  {len(unparsable)} files could not be parsed (skipped)."
        )

    if len(scanned_experiments) == 0:
        console.print("[yellow]No experiments found.[/yellow]")

    return scanned_experiments


@db_app.command("import")
def import_experiments(
    directory: Annotated[
        Path,
        typer.Argument(help="Directory containing experiment JSON files to import.", exists=True),
    ],
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Output DuckDB file path.")
    ] = paths.experiments_db,
    max_workers: Annotated[
        int, typer.Option("--max-workers", "-j", help="Parallel worker threads for scanning.")
    ] = 32,
) -> None:
    """Import experiment JSONs from DIRECTORY into a DuckDB file."""
    scanned_experiments = _scan_for_experiments(directory, max_workers=max_workers)
    if not scanned_experiments:
        raise typer.Exit(code=0)

    engine = get_engine(str(output))
    SQLModel.metadata.create_all(engine)

    with create_progress() as progress:
        write_task = progress.add_task("Writing to DuckDB", total=len(scanned_experiments))
        with Session(engine) as session:
            for row in scanned_experiments:
                _ = session.merge(row)
                progress.advance(write_task)
            session.commit()

    console.print(
        f"[green]\u2713[/green] Added "
        f"[green]{len(scanned_experiments)}[/green] rows "
        f"\u2192 [cyan]{output}[/cyan]"
    )


def validate_scanned_experiments_with_wandb(
    scanned_experiments: list[ScannedExperiment], wandb_path: str
) -> tuple[list[ScannedExperiment], list[ScannedExperiment]]:
    """Validate scanned experiments against wandb and filter out invalid ones.

    Queries wandb using paired (experiment_name, player_uuid) filters for precision.
    When ``updated_after`` is set, only runs updated since that timestamp are fetched
    (incremental sync). Experiments not returned by an incremental query keep their
    existing ``wandb_valid`` value.

    Mutates ``wandb_valid`` and ``wandb_last_updated`` on each ``ScannedExperiment``
    in place, then returns ``(valid_experiments, invalid_experiments)``.
    """
    exp_by_name = {exp.experiment_name: exp for exp in scanned_experiments}
    experiment_conditions = [
        {
            "$and": [
                {"config.experiment_name": exp.experiment_name},
                {
                    "config.player_uuid": {
                        "$in": [uuid for uuid in (exp.player_uuids or []) if uuid]
                    }
                },
            ]
        }
        for exp in scanned_experiments
        if any(uuid for uuid in (exp.player_uuids or []))  # skip experiments with no valid UUIDs
    ]

    additional_filters = [{"$or": experiment_conditions}] if experiment_conditions else []
    wandb_runs = get_runs_from_wandb(wandb_path, additional_filters=additional_filters)

    if not wandb_runs:
        return [], scanned_experiments

    invalid_runs = get_invalid_runs_from_collated_runs(
        collate_runs_per_experiment_per_game(wandb_runs)
    )
    invalid_names = {run.config["experiment_name"] for run in invalid_runs}
    all_wandb_names = {run.config["experiment_name"] for run in wandb_runs}
    valid_names = all_wandb_names - invalid_names

    for wandb_name in all_wandb_names:
        if wandb_name in exp_by_name:
            exp_by_name[wandb_name].is_wandb_valid = wandb_name in valid_names

    return (
        [exp for exp in scanned_experiments if exp.experiment_name in valid_names],
        [exp for exp in scanned_experiments if exp.experiment_name not in valid_names],
    )


@db_app.command("validate")
def validate_experiments(
    wandb_path: Annotated[
        str, typer.Option("--wandb-path", "-w", help="WandB project path (entity/project).")
    ],
    db_path: Annotated[
        Path,
        typer.Option(help="Path to the DuckDB file to validate.", file_okay=True, exists=True),
    ] = paths.experiments_db,
) -> None:
    """Validate experiment runs against WandB and update the wandb_valid column.

    Already-validated experiments are left untouched.
    """
    engine = get_engine(str(db_path))

    with Session(engine) as session:
        candidates = list(
            session.exec(
                select(ScannedExperiment).where(ScannedExperiment.is_wandb_valid == None)  # noqa: E711
            ).all()
        )

        if not candidates:
            console.print("[green]✓[/green]  All experiments already have is_wandb_valid set.")
            return

        console.print(
            f"Validating [cyan]{len(candidates)}[/cyan] experiments against"
            f" WandB [cyan]{wandb_path}[/cyan]"
        )

        valid, invalid = validate_scanned_experiments_with_wandb(candidates, wandb_path=wandb_path)

        # The returned experiments may be detached; re-fetch and mutate so SQLModel tracks changes
        names_valid = {exp.experiment_name for exp in valid}
        names_invalid = {exp.experiment_name for exp in invalid}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Scanning for experiment files", total=len(candidates))
            for exp in candidates:
                if exp.experiment_name in names_valid:
                    exp.is_wandb_valid = True
                    session.add(exp)
                elif exp.experiment_name in names_invalid:
                    exp.is_wandb_valid = False
                    session.add(exp)
                progress.advance(task)
            session.commit()

    console.print(f"[green]✓[/green]  {len(valid)} valid, [red]{len(invalid)}[/red] invalid.")
