from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pyarrow as pa
from pyarrow import parquet as pq

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.records.db._extract import BlobbedStepRecord, DumpedExperimentMetadata


def write_steps_batch(batch: list[BlobbedStepRecord], tmp_dir: Path) -> None:
    """Write a batch of step records to a uniquely-named parquet file in tmp_dir."""
    if not batch:
        return
    table = pa.Table.from_pylist(batch)
    pq.write_table(table, tmp_dir / f"steps_{uuid.uuid4().hex}.parquet")


def write_metadata(metadata: DumpedExperimentMetadata, tmp_dir: Path) -> None:
    """Write a single experiment metadata record to a uniquely-named parquet file in tmp_dir."""
    table = pa.Table.from_pylist([metadata])
    pq.write_table(table, tmp_dir / f"meta_{uuid.uuid4().hex}.parquet")
