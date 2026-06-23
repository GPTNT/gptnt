import os
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from cyclopts.types import ExistingDirectory
from rich.console import Console
from rich.progress import Progress

from gptnt.core.common.logger import create_progress
from gptnt.core.common.paths import Paths
from gptnt.experiments.cli.cleanup import cleanup_experiment_outputs
from gptnt.experiments.cli.models import SourceOption
from gptnt.experiments.db.ingest import extract_player_records_to_parquet, merge_parquet_into_db
from gptnt.experiments.db.validate import (
    get_all_experiments_from_db,
    get_non_validated_experiments_from_db,
    update_db_with_validation_results,
    validate_experiments_against_wandb,
)
from gptnt.experiments.ledger import Source
from gptnt.experiments.ledger.wandb import resolve_wandb_path

console = Console()

paths = Paths()


def _ingest_records(
    *,
    directory: Path,
    output_db: Path,
    tmp_dir: Path | None,
    max_workers: int,
    batch_size: int,
    skip_extraction: bool,
    skip_filtering: bool,
    keep_tmp_dir: bool,
    progress: Progress,
) -> None:
    """Extract player-record JSONs to parquet and merge them into the DuckDB database."""
    effective_tmp_dir = tmp_dir or (output_db.parent / ".ingest_tmp")

    if not skip_extraction:
        all_outputs = list(directory.rglob("*.json"))
        progress.console.print(f"Found [green]{len(all_outputs)}[/green] JSON files to process.")
        extract_player_records_to_parquet(
            player_record_paths=all_outputs,
            db_path=output_db,
            tmp_dir=effective_tmp_dir,
            max_workers=max_workers,
            batch_size=batch_size,
            progress=progress,
            skip_filtering=skip_filtering,
        )

    merge_parquet_into_db(
        tmp_dir=effective_tmp_dir, db_path=output_db, keep_tmp_dir=keep_tmp_dir, progress=progress
    )


def _validate_against_wandb(
    *, output_db: Path, force_validation: bool, progress: Progress
) -> None:
    """Validate experiments in the DB against WandB and persist the results."""
    if force_validation:
        non_validated_experiments = get_all_experiments_from_db(
            db_path=output_db, progress=progress
        )
    else:
        non_validated_experiments = get_non_validated_experiments_from_db(
            db_path=output_db, progress=progress
        )
    valid_scanned_experiments = validate_experiments_against_wandb(
        non_validated_experiments, wandb_path=resolve_wandb_path(), progress=progress
    )
    update_db_with_validation_results(
        valid_experiments=valid_scanned_experiments, db_path=output_db, progress=progress
    )


def build_metadata_database(
    directory: Annotated[
        ExistingDirectory,
        Parameter(
            help="Directory containing experiment JSON files to import.",
            env_var="EXPERIMENT_RECORDER",
        ),
    ],
    *,
    output_db: Annotated[
        Path,
        Parameter(
            name=("--output", "-o"), help="Output DuckDB file path.", env_var="EXPERIMENTS_DB"
        ),
    ] = paths.experiments_db,
    max_workers: Annotated[
        int | None,
        Parameter(
            name=("--max-workers", "-j"),
            help="Parallel worker processes for processing the large JSONs.",
        ),
    ] = None,
    batch_size: Annotated[
        int,
        Parameter(
            name="--batch-size",
            help="Number of step records per parquet batch file. Higher = faster ingestion but more RAM per worker.",
        ),
    ] = 1000,
    tmp_dir: Annotated[
        Path | None,
        Parameter(
            name="--tmp-dir",
            help="Directory for intermediate parquet files. Defaults to a '.ingest_tmp' folder next to the output DB. Point at a fast scratch disk to maximise throughput.",
        ),
    ] = None,
    skip_json_cleanup: Annotated[
        bool,
        Parameter(
            name="--skip-json-cleanup", help="Don't first cleanup all the wandb runs and outputs."
        ),
    ] = False,
    skip_filtering: Annotated[
        bool,
        Parameter(
            name="--skip-filtering",
            help="Skip filtering out already-ingested experiments before ingesting new ones.",
        ),
    ] = False,
    skip_extraction: Annotated[
        bool,
        Parameter(
            name="--skip-extraction",
            help="Skip the JSON-to-parquet extraction phase and load parquet files already present in tmp-dir directly into DuckDB. Requires --tmp-dir to point at the existing parquet files.",
        ),
    ] = False,
    keep_tmp_dir: Annotated[
        bool,
        Parameter(
            name="--keep-tmp-dir",
            help="Keep the intermediate parquet files in tmp-dir after a successful merge instead of deleting them.",
        ),
    ] = False,
    skip_ingestion: Annotated[
        bool,
        Parameter(
            name="--skip-ingestion",
            help="Skip the ingestion step and move onto the validation step (useful if you've already ingested and just want to re-run validation).",
        ),
    ] = False,
    force_validation: Annotated[
        bool,
        Parameter(
            name="--force-validation",
            help="[wandb] Force re-validation of all runs, even ones previously marked valid.",
        ),
    ] = False,
    delete_existing_db: Annotated[
        bool,
        Parameter(
            name="--delete-existing-db",
            help="If the output DuckDB file already exists, delete it before building the new one",
        ),
    ] = False,
    source: SourceOption = Source.local,
) -> None:
    """Build the local DuckDB experiment database from experiment JSON files.

    Ingestion already stamps each experiment's validity from its on-disk outcome, so the default
    `--source local` needs no W&B. `--source wandb` additionally cross-checks validity against the
    W&B runs (the maintainers' historical step).
    """
    resolved_max_workers = max_workers or os.cpu_count() or 1

    if delete_existing_db and output_db.exists():
        console.print(f"[red]Deleting existing database at {output_db}[/red]")
        output_db.unlink(missing_ok=True)
        output_db.with_name(f"{output_db.stem}.duckdb.wal").unlink(missing_ok=True)

    if not skip_json_cleanup:
        console.print(
            "[yellow]First, we're going to cleanup the JSON files before we build the db.[/yellow]"
        )
        cleanup_experiment_outputs(directory=directory, source=source)

    console.rule("[bold]Build Experiment Metadata DB[/bold]")

    with create_progress(extra_fields=["extra"]) as progress:
        if not skip_ingestion:
            _ingest_records(
                directory=directory,
                output_db=output_db,
                tmp_dir=tmp_dir,
                max_workers=resolved_max_workers,
                batch_size=batch_size,
                skip_extraction=skip_extraction,
                skip_filtering=skip_filtering,
                keep_tmp_dir=keep_tmp_dir,
                progress=progress,
            )

        if source is Source.wandb:
            _validate_against_wandb(
                output_db=output_db, force_validation=force_validation, progress=progress
            )
