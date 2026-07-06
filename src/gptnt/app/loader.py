from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import streamlit as st
import structlog

from gptnt.common.paths import Paths
from gptnt.experiments.db.connection import DuckDBConnection
from gptnt.experiments.db.schema import EXPORT_CONTEXT_MARKER
from gptnt.experiments.models import (
    ExperimentPlayerRecord,
    ExperimentRecord,
    ExperimentStep,
    ExperimentSummary,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import UUID4

    from gptnt.app.components.filters import Filters

logger = structlog.get_logger()
paths = Paths()


@dataclass
class ExperimentLoader:
    """Experiment browser and record loader backed by a DuckDB file.

    Attributes:
        db_path: Path to the `experiments.duckdb` file.
        filtered_experiments: Subset of `experiments` matching the current filters.
        applied_filters: The currently applied filter criteria, if any.
        selected_experiment: The experiment chosen in the browser UI.
    """

    db_path: Path

    filtered_experiments: list[ExperimentSummary] = field(default_factory=list)
    applied_filters: Filters | None = None

    selected_experiment: ExperimentSummary | None = field(default=None)

    skip_invalid_runs: bool = True

    @classmethod
    def create(cls, db_path: Path | None = None) -> ExperimentLoader:
        """Create a loader and immediately populate it from the database."""
        resolved = db_path or paths.experiments_db
        loader = cls(db_path=resolved)
        return loader

    def load_experiment_record(self, metadata: ExperimentSummary) -> ExperimentRecord | None:
        """Load the full experiment record for a given experiment metadata."""
        table = ExperimentStep.table_name()
        query = self.connection().execute(
            f"SELECT * FROM {table} WHERE session_id = ?",  # noqa: S608
            [str(metadata.session_id)],
        )
        col_names = [desc[0] for desc in query.description]
        rows = query.fetchall()

        steps_by_player: dict[UUID4, list[ExperimentStep]] = {}
        for row in rows:
            step = ExperimentStep.model_validate(
                dict(zip(col_names, row, strict=False)), context={"mode": EXPORT_CONTEXT_MARKER}
            )
            steps_by_player.setdefault(step.player_uuid, []).append(step)

        player_records = [
            ExperimentPlayerRecord.from_summary_and_steps(metadata, steps)
            for steps in steps_by_player.values()
        ]

        return ExperimentRecord.from_player_records(player_records=player_records)

    def save_tags(self, metadata: ExperimentSummary, tags: list[str]) -> None:
        """Persist tag changes for an experiment to DuckDB and update in-memory state."""
        _ = self.connection().execute(
            f"""
            UPDATE {ExperimentSummary.table_name()}
            SET tags = ?
            WHERE attempt_name = ?
            """,  # noqa: S608
            [tags, metadata.attempt_name],
        )

        # Mirror change in memory so the UI reflects it without a full refresh
        for exp in self.filtered_experiments:
            if exp.attempt_name == metadata.attempt_name:
                exp.tags = tags
                break

        if (
            self.selected_experiment is not None
            and self.selected_experiment.attempt_name == metadata.attempt_name
        ):
            self.selected_experiment.tags = tags

    @property
    def all_tags(self) -> set[str]:
        """All unique tags across all loaded experiments."""
        output = self.connection().execute(
            f"SELECT DISTINCT unnest(tags) AS tag FROM {ExperimentSummary.table_name()}"  # noqa: S608
        )
        return {row[0] for row in output.fetchall()}

    @property
    def db_exists(self) -> bool:
        """True if the DuckDB file is present on disk."""
        return self.db_path.exists()

    def connection(self) -> DuckDBConnection:
        """Get a DuckDB connection context manager for executing queries."""
        return st.connection("experiments", type=DuckDBConnection, database=self.db_path)

    def count_experiments(self, *, skip_invalid: bool) -> int:
        """Return the number of experiments matching the current filter."""
        query = f"SELECT COUNT(*) FROM {ExperimentSummary.table_name()}"  # noqa: S608

        if skip_invalid:
            query = f"{query} WHERE NOT is_hard_crash"
        row = self.connection().execute(query).fetchone()
        return row[0]  # pyright: ignore[reportOptionalSubscript]
