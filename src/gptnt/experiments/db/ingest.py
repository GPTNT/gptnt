from __future__ import annotations

import multiprocessing
from typing import TYPE_CHECKING, Any

import duckdb
import pyarrow as pa
import structlog

from gptnt.common.logger import ProgressSentinel, with_default_progress
from gptnt.experiments.db._extract import (
    extract_metadata_from_paths,
    filter_existing_experiments,
    group_by_unique_experiment,
)
from gptnt.experiments.db._schema import ensure_schema

if TYPE_CHECKING:
    from pathlib import Path

    from rich.progress import Progress

logger = structlog.get_logger()

# (summary row dict, the group's step files) — what one worker returns for a valid experiment.
type _GroupResult = tuple[dict[str, Any], list[Path]]


def _build_group_summary(file_paths: list[Path]) -> _GroupResult | None:
    """Derive one experiment's summary row from its footers; return it with its step files.

    Exceptions are logged and swallowed so a single bad experiment group doesn't kill the pool —
    returning None excludes its step files from the merge, so the experiment is skipped entirely
    (no orphan step rows).
    """
    try:
        summary = extract_metadata_from_paths(file_paths)
    except Exception:
        logger.exception("Error building summary from experiment files", file_paths=file_paths)
        return None
    return summary, file_paths


@with_default_progress()
def _build_all_summaries(
    grouped_paths: dict[str, list[Path]],
    *,
    max_workers: int,
    progress: Progress = ProgressSentinel,
) -> tuple[list[dict[str, Any]], list[Path]]:
    """Fan out summary-building across a worker pool; return (summary rows, step files)."""
    task = progress.add_task("Building summaries", total=len(grouped_paths))
    summaries: list[dict[str, Any]] = []
    step_paths: list[Path] = []
    with multiprocessing.Pool(processes=max_workers) as pool:
        for built in pool.imap_unordered(_build_group_summary, grouped_paths.values()):
            if built is not None:
                summary, group_paths = built
                summaries.append(summary)
                step_paths.extend(group_paths)
            progress.advance(task)
    return summaries, step_paths


def _execute_merge(
    *, summaries: list[dict[str, Any]], step_paths: list[Path], db_path: Path
) -> None:
    """Bulk-load step rows (from the recorder files) and summary rows (in memory) in one txn."""
    with duckdb.connect(db_path) as con:
        _ = con.execute(f"SET threads = {multiprocessing.cpu_count()}")
        _ = con.execute("SET preserve_insertion_order = false")
        _ = con.execute("SET checkpoint_threshold='16GB'")
        new_steps = con.read_parquet([str(path) for path in step_paths], union_by_name=True)
        new_summaries = pa.Table.from_pylist(summaries)
        _ = con.register("new_step_records", new_steps)
        _ = con.register("new_summaries", new_summaries)
        _ = con.begin()
        try:  # noqa: WPS229
            # Recorder parquet is already the step representation; BY NAME matches columns by name.
            _ = con.execute("INSERT INTO experiment_step BY NAME SELECT * FROM new_step_records")
            _ = con.execute("INSERT INTO experiment_summary BY NAME SELECT * FROM new_summaries")
        except Exception:
            _ = con.rollback()
            raise
        else:
            _ = con.commit()
        finally:
            _ = con.unregister("new_step_records")
            _ = con.unregister("new_summaries")


@with_default_progress()
def ingest_player_records(
    *,
    player_record_paths: list[Path],
    db_path: Path,
    max_workers: int = 6,
    skip_filtering: bool = False,
    progress: Progress = ProgressSentinel,
) -> None:
    """Ingest recorder parquet files into DuckDB.

    Recorder parquet is already the DuckDB-ready step representation, so step rows merge straight
    from the source files; the per-experiment summary is derived from the parquet footers in memory
    and inserted in the same transaction. Idempotent: experiments already present (matched on
    footer `(session_id, player_uuid)`) are filtered out first.
    """
    ensure_schema(db_path)

    if not skip_filtering:
        with duckdb.connect(db_path) as con:
            player_record_paths = filter_existing_experiments(
                file_paths=player_record_paths, connection=con, progress=progress
            )

    if not player_record_paths:
        logger.info("No new experiment files to ingest.")
        return

    grouped_paths = group_by_unique_experiment(sorted(player_record_paths))
    summaries, step_paths = _build_all_summaries(
        grouped_paths, max_workers=max_workers, progress=progress
    )
    if not summaries:
        logger.info("No valid experiments to merge after summary extraction.")
        return

    merge_task = progress.add_task("Merging into DuckDB...", total=None)
    _execute_merge(summaries=summaries, step_paths=step_paths, db_path=db_path)
    progress.update(merge_task, total=1, completed=1)
