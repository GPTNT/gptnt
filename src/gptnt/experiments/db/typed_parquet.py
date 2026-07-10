"""Typed list-of-pydantic-models ⇄ parquet round-trip via the DuckDB export context.

Serialises pydantic models to a parquet file (and back) using the same
`context={"mode": EXPORT_CONTEXT_MARKER}` serialization as the DuckDB export path: `AsJSON` fields
become JSON columns and `AsBlob` fields become compressed bytes, with the arrow schema inferred
from the dumped rows via `pa.Table.from_pylist`. The read side replays that context on
`model_validate` so JSON columns parse back into Python objects before validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow as pa
from pyarrow import parquet as pq
from pydantic import BaseModel

from gptnt.experiments.db.schema import EXPORT_CONTEXT_MARKER

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


def write_typed_parquet(rows: Sequence[BaseModel], *, file_path: Path) -> None:
    """Write pydantic models to parquet using the DuckDB export-context serialization."""
    parquet_rows = [row.model_dump(context={"mode": EXPORT_CONTEXT_MARKER}) for row in rows]
    _ = pq.write_table(pa.Table.from_pylist(parquet_rows), file_path)


def read_typed_parquet[ModelT: BaseModel](model: type[ModelT], file_path: Path) -> list[ModelT]:
    """Read a parquet file back into a list of `model` instances (JSON columns parse on input)."""
    table = pq.read_table(file_path)
    return [
        model.model_validate(parquet_row, context={"mode": EXPORT_CONTEXT_MARKER})
        for parquet_row in table.to_pylist()
    ]
