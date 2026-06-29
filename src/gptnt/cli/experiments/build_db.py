import os
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from cyclopts.types import ExistingDirectory
from rich.console import Console
from rich.progress import Progress

from gptnt.common.logger import create_progress
from gptnt.common.paths import Paths
from gptnt.experiments.db.ingest import ingest_player_records

console = Console()

paths = Paths()


def _ingest_records(
    *, directory: Path, output_db: Path, max_workers: int, skip_filtering: bool, progress: Progress
) -> None:
    """Ingest the recorder's parquet record files into the DuckDB database."""
    all_outputs = list(directory.rglob("experiment-*.parquet"))
    progress.console.print(f"Found [green]{len(all_outputs)}[/green] parquet files to process.")
    ingest_player_records(
        player_record_paths=all_outputs,
        db_path=output_db,
        max_workers=max_workers,
        skip_filtering=skip_filtering,
        progress=progress,
    )


def build_metadata_database(
    directory: Annotated[
        ExistingDirectory,
        Parameter(
            help="Directory containing experiment parquet record files to import.",
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
            help="Parallel worker processes for reading the parquet record footers.",
        ),
    ] = None,
    skip_filtering: Annotated[
        bool,
        Parameter(
            name="--skip-filtering",
            help="Skip filtering out already-ingested experiments before ingesting new ones.",
        ),
    ] = False,
    delete_existing_db: Annotated[
        bool,
        Parameter(
            name="--delete-existing-db",
            help="If the output DuckDB file already exists, delete it before building the new one",
        ),
    ] = False,
) -> None:
    """Build the local DuckDB experiment database from experiment parquet record files.

    Local and self-contained: each experiment's outcome (incl. `is_hard_crash`) comes straight from
    its parquet footer, so no W&B is needed. Cross-machine completion/validity is the ledger's job
    (see `gptnt.experiments.ledger`), not this command's.
    """
    resolved_max_workers = max_workers or os.cpu_count() or 1

    if delete_existing_db and output_db.exists():
        console.print(f"[red]Deleting existing database at {output_db}[/red]")
        output_db.unlink(missing_ok=True)
        output_db.with_name(f"{output_db.stem}.duckdb.wal").unlink(missing_ok=True)

    console.rule("[bold]Build Experiment Summary DB[/bold]")

    with create_progress(extra_fields=["extra"]) as progress:
        _ingest_records(
            directory=directory,
            output_db=output_db,
            max_workers=resolved_max_workers,
            skip_filtering=skip_filtering,
            progress=progress,
        )
