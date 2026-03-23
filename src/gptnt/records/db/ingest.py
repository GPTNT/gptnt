from __future__ import annotations

import multiprocessing
from typing import TYPE_CHECKING

import duckdb
import structlog

from gptnt.common.logger import ProgressSentinel, with_default_progress
from gptnt.records.db._extract import (
    extract_metadata_from_paths,
    filter_existing_experiments,
    group_by_unique_experiment,
    iter_blobbed_step_records,
)
from gptnt.records.db._schema import ensure_schema
from gptnt.records.db._writer import ExperimentDoneSignal, QueueDepthT, StepQueueT, WriterThread

if TYPE_CHECKING:
    from collections.abc import Iterator
    from multiprocessing.pool import Pool
    from pathlib import Path

    from rich.progress import Progress

logger = structlog.get_logger()


# Set once per worker process by _worker_init — never written from the main process.
_step_queue: StepQueueT | None = None
_queue_depth: QueueDepthT | None = None


def _worker_init(step_queue: StepQueueT, queue_depth: QueueDepthT) -> None:
    global _step_queue, _queue_depth  # noqa: PLW0603, WPS420
    _step_queue = step_queue
    _queue_depth = queue_depth


def _stream_experiment_to_queue(file_paths: list[Path]) -> None:
    """Extract and push one experiment's data — called inside a try/except by the pool worker."""
    assert _step_queue is not None, "Worker not initialised"
    assert _queue_depth is not None, "Worker not initialised"
    metadata = extract_metadata_from_paths(file_paths)
    for record in iter_blobbed_step_records(file_paths):
        with _queue_depth.get_lock():
            _queue_depth.value += 1
        _step_queue.put(record)  # blocks when queue is full — natural back-pressure
    with _queue_depth.get_lock():
        _queue_depth.value += 1
    _step_queue.put(ExperimentDoneSignal(metadata=metadata))


def extract_and_enqueue(file_paths: list[Path]) -> None:
    """Extract experiment data and stream it directly into the writer queue.

    Step records are pushed one at a time through a bounded queue. The worker blocks on queue.put()
    when the queue is full, providing structural back-pressure that stops disk reads when the
    writer cannot keep up. An ExperimentDoneSignal is pushed last so the writer knows when all step
    records for an experiment have been enqueued and can commit the metadata.

    Exceptions are logged and swallowed so a single bad experiment group doesn't kill the pool.
    """
    try:
        _stream_experiment_to_queue(file_paths)
    except Exception:
        logger.exception("Error extracting data from experiment files", file_paths=file_paths)


def _cleanup_orphaned_step_records(connection: duckdb.DuckDBPyConnection) -> None:
    """Remove step records that have no corresponding experiment metadata entry.

    These can arise if ingestion was interrupted after step records were written but before the
    ExperimentDoneSignal was processed and the metadata committed.
    """
    _ = connection.execute(
        "DELETE FROM experiment_step_record "
        "WHERE session_id NOT IN (SELECT session_id FROM experiment_metadata)"
    )


@with_default_progress()
def extract_all_data(
    grouped_paths: dict[str, list[Path]], *, pool: Pool, progress: Progress = ProgressSentinel
) -> Iterator[None]:
    """Submit all groups to the pool; workers stream results directly to the writer queue.

    Yields once per completed group so the caller can poll for writer errors between completions.
    """
    task = progress.add_task("Extracting data", total=len(grouped_paths))
    for _ in pool.imap_unordered(extract_and_enqueue, grouped_paths.values()):
        progress.advance(task)
        yield


@with_default_progress()
def ingest_player_records(
    *,
    player_record_paths: list[Path],
    db_path: Path,
    max_workers: int = 6,
    step_queue_size: int = 500,
    writer_batch_size: int = 100,
    progress: Progress = ProgressSentinel,
    skip_filtering: bool = False,
) -> None:
    """Ingest experiment JSON files into DuckDB with bounded memory usage.

    Step records are streamed one at a time through a bounded queue. Workers block when the queue
    is full, providing structural back-pressure that limits peak memory regardless of individual
    file sizes. A single writer thread owns the DuckDB connection and flushes in batches of 100.
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

    with WriterThread(
        db_path=db_path,
        progress=progress,
        step_queue_size=step_queue_size,
        writer_batch_size=writer_batch_size,
        num_experiments=len(grouped_paths),
    ) as writer:
        with multiprocessing.Pool(
            processes=max_workers,
            initializer=_worker_init,
            initargs=(writer.step_queue, writer.queue_depth),
        ) as pool:
            for _ in extract_all_data(grouped_paths, pool=pool, progress=progress):
                writer.check()

        if writer.error_event.is_set():
            raise RuntimeError(
                "Ingestion completed but the writer thread encountered errors — check logs"
            )
