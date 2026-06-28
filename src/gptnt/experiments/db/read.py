"""Read experiment summaries from the DuckDB results database."""

from __future__ import annotations

from typing import TYPE_CHECKING

import duckdb

from gptnt.experiments.models import ExperimentSummary

if TYPE_CHECKING:
    from pathlib import Path


def load_summaries(db_path: Path) -> list[ExperimentSummary]:
    """Load every experiment summary row from the DuckDB database."""
    with duckdb.connect(str(db_path), read_only=True) as con:
        output = con.execute(f"SELECT * FROM {ExperimentSummary.table_name()}")  # noqa: S608
        columns = [desc[0] for desc in output.description]
        return [
            ExperimentSummary.model_validate(dict(zip(columns, row, strict=False)))
            for row in output.fetchall()
        ]
