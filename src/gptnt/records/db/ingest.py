from __future__ import annotations

import multiprocessing
from typing import TYPE_CHECKING

import duckdb
import structlog

from gptnt.common.logger import ProgressSentinel, with_default_progress
from gptnt.records.db._extract import (
    extract_combined_from_paths,
    filter_existing_experiments,
    group_by_unique_experiment,
)
from gptnt.records.db._schema import ensure_schema
from gptnt.records.db._writer import QueueDepthT, WriteQueueT, WriterThread

if TYPE_CHECKING:
    from collections.abc import Iterator
    from multiprocessing.pool import Pool
    from multiprocessing.synchronize import Semaphore
    from pathlib import Path

    from rich.progress import Progress

logger = structlog.get_logger()


# Set once per worker process by _worker_init — never written from the main process.
_write_queue: WriteQueueT | None = None
_queue_depth: QueueDepthT | None = None
_semaphore: Semaphore | None = None


def _worker_init(queue: WriteQueueT, depth: QueueDepthT, semaphore: Semaphore) -> None:
    global _write_queue, _queue_depth, _semaphore  # noqa: PLW0603, WPS420
    _write_queue = queue
    _queue_depth = depth
    _semaphore = semaphore


def extract_and_enqueue(file_paths: list[Path]) -> None:
    """Extract experiment data and push directly to the writer queue.

    The main process is bypassed entirely — data flows worker → queue → writer thread. Exceptions
    are swallowed here so a single bad experiment group doesn't kill the pool.
    """
    assert _write_queue is not None, "Worker not initialised"
    assert _queue_depth is not None, "Worker not initialised"
    assert _semaphore is not None, "Worker not initialised"

    # Block here if the queue is full
    _ = _semaphore.acquire()

    try:
        _write_queue.put(extract_combined_from_paths(file_paths))
    except Exception:
        logger.exception("Error extracting data from experiment files", file_paths=file_paths)
        # release the slot so the pool doesn't stall; the writer thread will skip this item since it was never enqueued
        _semaphore.release()

    with _queue_depth.get_lock():
        _queue_depth.value += 1


@with_default_progress()
def extract_all_data(
    grouped_paths: dict[str, list[Path]], *, pool: Pool, progress: Progress = ProgressSentinel
) -> Iterator[None]:
    """Submit all groups to the pool; workers push results directly to the write queue.

    Yields once per completed group so the caller can poll for writer errors between completions
    without needing access to pool internals.
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
    max_queue_size: int = 100,
    progress: Progress = ProgressSentinel,
    skip_filtering: bool = False,
) -> None:
    """Ingest experiment JSON files into DuckDB in a single extraction pass.

    Each file group is processed exactly once — metadata and step records are extracted together in
    the same worker call. A dedicated write thread runs concurrently so DuckDB writes and CPU-bound
    reads overlap rather than serialise.
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

    with WriterThread(
        db_path=db_path,
        progress=progress,
        queue_size=max_queue_size,
        num_experiments=len(grouped_paths),
    ) as writer:
        with multiprocessing.Pool(
            processes=max_workers,
            initializer=_worker_init,
            initargs=(writer.queue, writer.queue_depth, writer.semaphore),
        ) as pool:
            for _ in extract_all_data(grouped_paths, pool=pool, progress=progress):
                writer.check()

        if writer.error_event.is_set():
            raise RuntimeError(
                "Ingestion completed but the writer thread encountered errors — check logs"
            )
