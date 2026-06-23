from __future__ import annotations

import contextlib
import multiprocessing
import shutil
from functools import partial
from typing import TYPE_CHECKING, Any

import duckdb
import structlog

from gptnt.core.common.logger import ProgressSentinel, with_default_progress
from gptnt.experiments.db._extract import (
    extract_metadata_from_paths,
    filter_existing_experiments,
    group_by_unique_experiment,
    iter_blobbed_step_records,
)
from gptnt.experiments.db._parquet_writer import write_metadata, write_steps_batch
from gptnt.experiments.db._schema import ensure_schema

if TYPE_CHECKING:
    from pathlib import Path

    from rich.progress import Progress

logger = structlog.get_logger()


def _extract_experiment_to_parquet(
    file_paths: list[Path], *, tmp_dir: Path, batch_size: int
) -> None:
    """Extract one experiment's data and write it to parquet files — no queue, no contention."""
    batch = []
    for record in iter_blobbed_step_records(file_paths):
        batch.append(record)
        if len(batch) >= batch_size:
            write_steps_batch(batch, tmp_dir)
            batch = []
    if batch:
        write_steps_batch(batch, tmp_dir)
    write_metadata(extract_metadata_from_paths(file_paths), tmp_dir)


def extract_to_parquet(file_paths: list[Path], **kwargs: Any) -> None:
    """Extract experiment data and write it to parquet files in the worker-local tmp_dir.

    Exceptions are logged and swallowed so a single bad experiment group doesn't kill the pool.
    """
    try:
        _extract_experiment_to_parquet(file_paths, **kwargs)
    except Exception:
        logger.exception("Error extracting data from experiment files", file_paths=file_paths)


def _cleanup_orphaned_step_records(connection: duckdb.DuckDBPyConnection) -> None:
    """Remove step records that have no corresponding experiment metadata entry.

    These can arise if ingestion was interrupted before metadata was committed.
    """
    _ = connection.execute(
        "DELETE FROM experiment_step_record "
        "WHERE session_id NOT IN (SELECT session_id FROM experiment_metadata)"
    )


def _prepare_tmp_dir(tmp_dir: Path) -> None:
    """Delete any leftover tmp dir from a previous crashed run, then create it fresh."""
    if tmp_dir.exists():
        logger.warning("Leftover tmp dir found — removing (crash recovery)", path=tmp_dir)
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)


@with_default_progress()
def _extract_all_to_parquet(
    grouped_paths: dict[str, list[Path]],
    *,
    tmp_dir: Path,
    max_workers: int,
    batch_size: int,
    progress: Progress = ProgressSentinel,
) -> None:
    """Fan out extraction across a worker pool; each worker writes parquet files to tmp_dir."""
    task = progress.add_task("Extracting data", total=len(grouped_paths))
    with multiprocessing.Pool(processes=max_workers) as pool:
        for _ in pool.imap_unordered(
            partial(extract_to_parquet, tmp_dir=tmp_dir, batch_size=batch_size),
            grouped_paths.values(),
        ):
            progress.advance(task)


def _execute_parquet_merge(tmp_dir: Path, db_path: Path) -> None:
    """Bulk-load all parquet files from tmp_dir into DuckDB in a single transaction."""
    steps_glob = str(tmp_dir / "steps_*.parquet")
    meta_glob = str(tmp_dir / "meta_*.parquet")

    with duckdb.connect(db_path) as con:
        _ = con.execute(f"SET threads = {multiprocessing.cpu_count()}")
        _ = con.execute("SET preserve_insertion_order = false")
        _ = con.execute("SET checkpoint_threshold='16GB'")
        _ = con.begin()
        try:  # noqa: WPS229
            _ = con.execute(
                f"INSERT INTO experiment_step_record SELECT * FROM read_parquet('{steps_glob}', union_by_name=true)"  # noqa: S608
            )
            _ = con.execute(
                f"INSERT INTO experiment_metadata SELECT * FROM read_parquet('{meta_glob}', union_by_name=true)"  # noqa: S608
            )
        except Exception:
            _ = con.rollback()
            raise
        else:
            _ = con.commit()


@with_default_progress()
def extract_player_records_to_parquet(
    *,
    player_record_paths: list[Path],
    db_path: Path,
    tmp_dir: Path,
    max_workers: int = 6,
    batch_size: int = 100,
    progress: Progress = ProgressSentinel,
    skip_filtering: bool = False,
) -> None:
    """Stage 1: filter, group, and extract experiment JSON files to intermediate parquet files.

    Each worker process extracts and writes parquet files independently — no shared queue, no
    serialization point. If tmp_dir already exists at startup it is deleted (crash recovery).
    """
    ensure_schema(db_path)

    with duckdb.connect(db_path) as con:
        _cleanup_orphaned_step_records(con)
        if not skip_filtering:
            player_record_paths = filter_existing_experiments(
                file_paths=player_record_paths, connection=con, progress=progress
            )

    if not player_record_paths:
        logger.info("No new experiment files to ingest.")
        return

    grouped_paths = group_by_unique_experiment(sorted(player_record_paths))
    _prepare_tmp_dir(tmp_dir)
    _extract_all_to_parquet(
        grouped_paths,
        tmp_dir=tmp_dir,
        max_workers=max_workers,
        batch_size=batch_size,
        progress=progress,
    )


@with_default_progress()
def merge_parquet_into_db(
    *,
    tmp_dir: Path,
    db_path: Path,
    keep_tmp_dir: bool = False,
    progress: Progress = ProgressSentinel,
) -> None:
    """Stage 2: bulk-load all parquet files from tmp_dir into DuckDB.

    Cleans up tmp_dir on completion unless keep_tmp_dir is True. Safe to call standalone after a
    failed run — re-runs ensure_schema and orphan cleanup before merging.
    """
    ensure_schema(db_path)

    with duckdb.connect(db_path) as con:
        _cleanup_orphaned_step_records(con)

    with contextlib.ExitStack() as stack:
        if not keep_tmp_dir:
            _ = stack.callback(shutil.rmtree, tmp_dir, ignore_errors=True)
        merge_task = progress.add_task("Merging into DuckDB...", total=None)
        _execute_parquet_merge(tmp_dir, db_path)
        progress.update(merge_task, total=1, completed=1)
