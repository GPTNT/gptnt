from __future__ import annotations

import multiprocessing
import queue
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Self

import duckdb
import pyarrow as pa
import structlog

from gptnt.records.models import ExperimentMetadata, ExperimentStepRecord

if TYPE_CHECKING:
    from multiprocessing.queues import Queue
    from multiprocessing.sharedctypes import Synchronized
    from pathlib import Path

    from rich.progress import Progress, TaskID

    from gptnt.common.duckdb import DuckDBSchemaMixin
    from gptnt.records.db._extract import BlobbedStepRecord, DumpedExperimentMetadata

logger = structlog.get_logger()


class StopSignal:
    """Picklable sentinel — tells the writer thread to stop consuming the queue."""


@dataclass
class ExperimentDoneSignal:
    """Carries metadata for a completed experiment.

    Pushed by a worker after all its step records have been enqueued. Tells the writer to flush any
    buffered steps and then commit the metadata row.
    """

    metadata: DumpedExperimentMetadata


type StepQueueT = Queue[BlobbedStepRecord | ExperimentDoneSignal | StopSignal]
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
    """Background DuckDB write thread that consumes a stream of individual step records.

    Workers push BlobbedStepRecord items one at a time through a bounded queue, then push an
    ExperimentDoneSignal when all step records for that experiment have been enqueued. The bounded
    queue provides structural back-pressure: workers block on queue.put() when it is full, which
    naturally stops them reading from disk. Peak memory is bounded by step_queue_size regardless of
    individual file sizes.

    Use as a context manager:

        with WriterThread(...) as writer:
            writer.check()
    """

    db_path: Path
    progress: Progress
    num_experiments: int

    step_queue_size: int = 500
    writer_batch_size: int = 100
    join_timeout: float = 60

    error_event: threading.Event = field(init=False, default_factory=threading.Event)
    step_queue: StepQueueT = field(init=False)
    queue_depth: QueueDepthT = field(init=False)

    _thread: threading.Thread = field(init=False)
    _write_task: TaskID = field(init=False, repr=False)
    _queue_task: TaskID = field(init=False, repr=False)
    _steps_task: TaskID = field(init=False, repr=False)
    _batch_task: TaskID = field(init=False, repr=False)

    def __post_init__(self) -> None:
        ctx = multiprocessing.get_context()
        self.step_queue = ctx.Queue(maxsize=self.step_queue_size)
        self.queue_depth = ctx.Value("i", 0)
        self._thread = threading.Thread(target=self._run, daemon=True, name="duckdb-writer")

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
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
                "[dim]Queue depth[/]", total=self.step_queue_size, completed=0
            )
        return self._queue_task

    @property
    def steps_task(self) -> TaskID:
        if not hasattr(self, "_steps_task"):
            self._steps_task = self.progress.add_task(
                "[dim]Step records written[/]", total=None, completed=0
            )
        return self._steps_task

    @property
    def batch_task(self) -> TaskID:
        if not hasattr(self, "_batch_task"):
            self._batch_task = self.progress.add_task(
                "[dim]Batch size[/]", total=self.writer_batch_size, completed=0
            )
        return self._batch_task

    def check(self) -> None:
        """Raise immediately if the writer thread has crashed."""
        if self.error_event.is_set():
            raise RuntimeError("Writer thread failed — check logs above")

    def _run(self) -> None:
        try:
            with duckdb.connect(self.db_path) as con:
                # Checkpointing after every batch is a huge slowdown, so we set a high threshold
                _ = con.execute("SET checkpoint_threshold='16GB'")
                # We don't care about insertion order so let DuckDB parallelise where possible
                _ = con.execute("SET preserve_insertion_order = false")
                _ = con.execute(f"SET threads = {multiprocessing.cpu_count()}")
                self._drain(con)
        except Exception:
            logger.exception("Writer thread encountered an error")
            self.error_event.set()

    def _drain(self, con: duckdb.DuckDBPyConnection) -> None:
        """Consume the step queue until StopSignal, flushing step batches along the way."""
        step_batch: list[BlobbedStepRecord] = []

        while True:
            msg = self.step_queue.get()

            if isinstance(msg, StopSignal):
                # StopSignal is put by _stop() without incrementing queue_depth, so don't decrement
                if step_batch:
                    self._flush_steps(step_batch, con)
                break

            with self.queue_depth.get_lock():
                self.queue_depth.value -= 1
            self.progress.update(self.queue_task, completed=self.queue_depth.value)

            if isinstance(msg, ExperimentDoneSignal):
                _ = self._on_experiment_done(msg, con)
                continue

            step_batch = self._accumulate(msg, step_batch, con)

    def _on_experiment_done(
        self, msg: ExperimentDoneSignal, con: duckdb.DuckDBPyConnection
    ) -> None:
        """Flush buffered steps then write the experiment metadata row."""
        self._write_metadata(msg.metadata, con)
        self.progress.update(self.write_task, advance=1)

    def _accumulate(
        self,
        record: BlobbedStepRecord,
        step_batch: list[BlobbedStepRecord],
        con: duckdb.DuckDBPyConnection,
    ) -> list[BlobbedStepRecord]:
        """Append a step record to the batch, flushing when it reaches capacity."""
        step_batch.append(record)
        self.progress.update(self.batch_task, completed=len(step_batch))
        if len(step_batch) >= self.writer_batch_size:
            self._flush_steps(step_batch, con)
            self.progress.update(self.batch_task, completed=0)
            return []
        return step_batch

    def _flush_steps(self, batch: list[BlobbedStepRecord], con: duckdb.DuckDBPyConnection) -> None:
        _ = con.begin()
        try:
            _ingest_batch(batch, model_type=ExperimentStepRecord, connection=con)
        except Exception:
            _ = con.rollback()
            raise
        else:
            _ = con.commit()
        self.progress.update(self.steps_task, advance=len(batch))

    def _write_metadata(
        self, metadata: DumpedExperimentMetadata, con: duckdb.DuckDBPyConnection
    ) -> None:
        _ = con.begin()
        try:
            _ingest_batch([metadata], model_type=ExperimentMetadata, connection=con)
        except Exception:
            _ = con.rollback()
            raise
        else:
            _ = con.commit()

    def _stop(self) -> None:
        try:
            self.step_queue.put(StopSignal(), timeout=30)
        except queue.Full:
            # The writer thread has likely crashed and is no longer draining the queue.
            logger.warning(
                "Could not enqueue StopSignal (queue full); writer thread may have crashed"
            )
        self._thread.join(timeout=self.join_timeout)
        if self._thread.is_alive():
            logger.error("Writer thread did not terminate cleanly")
