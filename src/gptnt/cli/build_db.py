import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from gptnt.cli._fields import WandbEntityOption, WandbProjectOption
from gptnt.cli.cleanup import cleanup_experiment_outputs
from gptnt.common.logger import create_progress
from gptnt.common.paths import Paths
from gptnt.records.db.ingest import ingest_player_records
from gptnt.records.db.validate import (
    get_all_experiments_from_db,
    get_non_validated_experiments_from_db,
    update_db_with_validation_results,
    validate_experiments_against_wandb,
)

console = Console()

paths = Paths()


def build_metadata_database(
    *,
    directory: Annotated[
        Path,
        typer.Argument(
            help="Directory containing experiment JSON files to import.",
            exists=True,
            envvar="EXPERIMENT_RECORDER",
        ),
    ],
    output_db: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output DuckDB file path.", envvar="EXPERIMENTS_DB"),
    ] = paths.experiments_db,
    max_workers: Annotated[
        int,
        typer.Option(
            "--max-workers",
            "-j",
            help="Parallel worker processes for processing the large JSONs.",
            default_factory=os.cpu_count,
        ),
    ],
    step_queue_size: Annotated[
        int,
        typer.Option(
            "--step-queue-size",
            help="Maximum step records buffered in the write queue. Lower = less peak RAM.",
            default_factory=lambda: 500,
        ),
    ],
    writer_batch_size: Annotated[
        int,
        typer.Option(
            "--writer-batch-size",
            help="Number of step records the writer thread inserts in a single transaction. Higher = faster ingestion but more RAM usage.",
        ),
    ] = 100,
    skip_json_cleanup: Annotated[
        bool,
        typer.Option(
            "--skip-json-cleanup", help="Don't first cleanup all the wandb runs and outputs."
        ),
    ] = False,
    skip_filtering: Annotated[
        bool,
        typer.Option(
            "--skip-filtering",
            help="Skip filtering out already-ingested experiments before ingesting new ones.",
        ),
    ] = False,
    skip_ingestion: Annotated[
        bool,
        typer.Option(
            "--skip-ingestion",
            help="Skip the ingestion step and move onto the validation step (useful if you've already ingested and just want to re-run validation).",
        ),
    ] = False,
    skip_validation: Annotated[
        bool,
        typer.Option(
            "--skip-validation",
            help="Don't validate runs against WandB, just import everything as-is (not recommended).",
        ),
    ] = False,
    force_validation: Annotated[
        bool,
        typer.Option(
            "--force-validation",
            help="Force re-validation of all runs against WandB, even if they were previously marked as valid (useful if you want to re-validate against a different WandB project or after fixing some issue with the validation).",
        ),
    ] = False,
    delete_existing_db: Annotated[
        bool,
        typer.Option(
            "--delete-existing-db",
            help="If the output DuckDB file already exists, delete it before building the new one",
        ),
    ] = False,
    wandb_entity: WandbEntityOption,
    wandb_project: WandbProjectOption,
) -> None:
    """Build the local DuckDB experiment database from experiment JSON files."""
    if delete_existing_db and output_db.exists():
        console.print(f"[red]Deleting existing database at {output_db}[/red]")
        output_db.unlink(missing_ok=True)
        output_db.with_name(f"{output_db.stem}.duckdb.wal").unlink(missing_ok=True)

    if not skip_json_cleanup:
        console.print(
            "[yellow]First, we're going to cleanup the JSON files before we build the db.[/yellow]"
        )
        cleanup_experiment_outputs(
            directory=directory, wandb_entity=wandb_entity, wandb_project=wandb_project
        )

    console.rule("[bold]Build Experiment Metadata DB[/bold]")

    with create_progress(extra_fields=["extra"]) as progress:
        if not skip_ingestion:
            all_outputs = list(directory.rglob("*.json"))
            progress.console.print(
                f"Found [green]{len(all_outputs)}[/green] JSON files to process."
            )

            ingest_player_records(
                player_record_paths=all_outputs,
                db_path=output_db,
                max_workers=max_workers,
                progress=progress,
                skip_filtering=skip_filtering,
                step_queue_size=step_queue_size,
                writer_batch_size=writer_batch_size,
            )

        if not skip_validation:
            if force_validation:
                non_validated_experiments = get_all_experiments_from_db(
                    db_path=output_db, progress=progress
                )
            else:
                non_validated_experiments = get_non_validated_experiments_from_db(
                    db_path=output_db, progress=progress
                )
            valid_scanned_experiments = validate_experiments_against_wandb(
                non_validated_experiments,
                wandb_path=f"{wandb_entity}/{wandb_project}",
                progress=progress,
            )
            update_db_with_validation_results(
                valid_experiments=valid_scanned_experiments, db_path=output_db, progress=progress
            )
