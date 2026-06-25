from pathlib import Path

import duckdb

from gptnt.experiments.models import ExperimentStep, ExperimentSummary


def ensure_schema(db_path: Path) -> None:
    """Create all tables in the database if they do not already exist.

    Safe to call repeatedly — all statements use IF NOT EXISTS.
    """
    with duckdb.connect(db_path) as con:
        ExperimentSummary.create_table(con)
        ExperimentStep.create_table(con)
