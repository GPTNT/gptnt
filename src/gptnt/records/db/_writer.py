from __future__ import annotations

import multiprocessing
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Self

import duckdb
import pyarrow as pa
import structlog

from gptnt.records.models import ExperimentMetadata, ExperimentStepRecord

if TYPE_CHECKING:
    from multiprocessing.queues import Queue
    from multiprocessing.sharedctypes import Synchronized
    from multiprocessing.synchronize import Semaphore
    from pathlib import Path

    from rich.progress import Progress, TaskID

    from gptnt.common.duckdb import DuckDBSchemaMixin
    from gptnt.records.db._extract import CombinedExperimentData

logger = structlog.get_logger()


class StopSignal:
    """Picklable sentinel — tells the writer thread to stop consuming the queue."""


type WriteQueueT = Queue[CombinedExperimentData | StopSignal]
type QueueDepthT = Synchronized[int]


def _ingest_batch(
    batch: list[dict[str, Any]],
    *,
    model_type: type[DuckDBSchemaMixin],
    connection: duckdb.DuckDBPyConnection,
) -> None:
    """Write a batch of records to DuckDB via an in-memory PyArrow table."""
    table = pa.Table.from_pylist(batch)
    _ = connection.register("_batch", table)
    _ = connection.execute(f"INSERT INTO {model_type.table_name()} SELECT * FROM _batch")  # noqa: S608
    _ = connection.unregister("_batch")


@dataclass(kw_only=True)
class WriterThread:
    """Background DuckDB write thread with a bounded input queue.

    Owns its own DuckDB connection so writes overlap with CPU-bound extraction
    in the process pool without serialising on a shared connection.

    Use as a context manager::

        with WriterThread(...) as writer:
            for item in source:
                writer.check()
    """

    db_path: Path
    progress: Progress
    num_experiments: int

    queue_size: int = 256
    join_timeout: float = 10
    batch_size: int = 16

    error_event: threading.Event = field(init=False, default_factory=threading.Event)
    queue: WriteQueueT = field(init=False)
    queue_depth: QueueDepthT = field(init=False)
    semaphore: Semaphore = field(init=False)

    _thread: threading.Thread = field(init=False)
    _monitor_thread: threading.Thread = field(init=False)
    _stop_monitor: threading.Event = field(init=False, default_factory=threading.Event)

    _write_task: TaskID = field(init=False, repr=False)
    _queue_task: TaskID = field(init=False, repr=False)
    _batch_task: TaskID = field(init=False, repr=False)

    def __post_init__(self) -> None:
        ctx = multiprocessing.get_context()
        self.queue = ctx.Queue(maxsize=self.queue_size)
        self.queue_depth = ctx.Value("i", 0)

        # allow some leeway over the max queue size
        self.semaphore = ctx.Semaphore(self.queue_size)

        self._thread = threading.Thread(target=self._run, daemon=True, name="duckdb-writer")
        self._monitor_thread = threading.Thread(
            target=self._monitor, daemon=True, name="queue-monitor"
        )

        # Just make sure the batch isnt bigger than the queue
        self.batch_size = min(self.batch_size, self.queue_size)

    def __enter__(self) -> Self:
        self._thread.start()
        self._monitor_thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop_monitor.set()
        self._monitor_thread.join()
        self._stop()

    @property
    def write_task(self) -> TaskID:
        if not hasattr(self, "_write_task"):
            self._write_task = self.progress.add_task(
                "Writing experiments", total=self.num_experiments
            )
        return self._write_task

    @property
    def queue_task(self) -> TaskID:
        if not hasattr(self, "_queue_task"):
            self._queue_task = self.progress.add_task(
                "Queue depth", total=self.queue_size, completed=0
            )
        return self._queue_task

    @property
    def batch_task(self) -> TaskID:
        if not hasattr(self, "_batch_task"):
            self._batch_task = self.progress.add_task(
                "Batch size", total=self.batch_size, completed=0
            )
        return self._batch_task

    def check(self) -> None:
        """Raise immediately if the writer thread has crashed."""
        if self.error_event.is_set():
            raise RuntimeError("Writer thread failed — check logs above")

    def _run(self) -> None:
        try:
            with duckdb.connect(self.db_path) as con:
                # Checkpointing after every batch is a huge slowdown, so we set a high threshold so
                # it doesnt do that.
                _ = con.execute("SET checkpoint_threshold='16GB'")
                # Also we dont care about the order so let it do things in parallel where possible
                _ = con.execute("SET preserve_insertion_order = false")
                # While it should default to this anyway, lets just be explicit best we can
                _ = con.execute(f"SET threads = {multiprocessing.cpu_count()}")
                while self._step(con):  # noqa: WPS328
                    pass  # noqa: WPS420
        except Exception:
            logger.exception("Writer thread encountered an error")
            self.error_event.set()

    def _step(self, con: duckdb.DuckDBPyConnection) -> bool:
        """Build and flush one batch.

        Returns False when a StopSignal is received.
        """
        batch: list[CombinedExperimentData] = []

        for _ in range(self.batch_size):
            data = self._pull_from_queue()
            if isinstance(data, StopSignal):
                if batch:
                    self._flush(batch, con)
                return False  # stop the loop
            batch.append(data)
            self.progress.update(self.batch_task, completed=len(batch))

        if batch:
            self._flush(batch, con)

        return True  # keep going

    def _flush(self, batch: list[CombinedExperimentData], con: duckdb.DuckDBPyConnection) -> None:
        all_metadata = [metadata for metadata, _ in batch]
        all_steps = [step for _, steps in batch for step in steps]
        _ = con.begin()
        try:  # noqa: WPS229
            _ingest_batch(all_metadata, model_type=ExperimentMetadata, connection=con)
            _ingest_batch(all_steps, model_type=ExperimentStepRecord, connection=con)
        except Exception:
            _ = con.rollback()
            raise
        else:
            _ = con.commit()
        self.progress.update(self.write_task, advance=len(batch))
        self.progress.update(self.batch_task, completed=0)

    def _monitor(self) -> None:
        # Touch both tasks here to ensure they're created on the main thread
        # before _run starts updating batch_task directly
        _ = self.queue_task
        _ = self.batch_task
        while not self._stop_monitor.is_set():
            self.progress.update(self.queue_task, completed=self.queue_depth.value)
            time.sleep(0.1)

    def _stop(self) -> None:
        self.queue.put(StopSignal())
        self._thread.join(timeout=self.join_timeout)
        if self._thread.is_alive():
            logger.error("Writer thread did not terminate cleanly")

    def _pull_from_queue(self) -> CombinedExperimentData | StopSignal:
        """Pull a single item from the queue, blocking until one is available."""
        data = self.queue.get()
        with self.queue_depth.get_lock():
            self.queue_depth.value -= 1
        if not isinstance(data, StopSignal):
            # slot is free, allow another worker to extract
            self.semaphore.release()
        return data
