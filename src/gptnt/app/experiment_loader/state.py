from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import streamlit as st
import structlog
from sqlmodel import select

from gptnt.app.experiment_loader.db_connection import DuckDBConnection
from gptnt.app.experiment_loader.scanner import ScannedExperiment
from gptnt.common.paths import Paths
from gptnt.players.metrics.records import (
    ExperimentPlayerRecord,
    ExperimentRecord,
    build_experiment_records_from_player_records,
)

if TYPE_CHECKING:
    from gptnt.app.components.filters import Filters

logger = structlog.get_logger()
paths = Paths()


@dataclass
class ExperimentLoader:
    """Experiment browser and record loader backed by a DuckDB file.

    Attributes:
        db_path: Absolute (or resolvable) path to the `experiments.duckdb` file.
        scanned_experiments: In-memory list of experiment metadata rows,
            populated on creation and on :meth:`refresh`.
        filtered_experiments: Subset of `scanned_experiments` matching the current filter criteria.
        applied_filters: The currently applied filter criteria, if any.
        selected_experiment: The experiment chosen in the browser UI.
    """

    db_path: str

    scanned_experiments: list[ScannedExperiment] = field(default_factory=list)
    filtered_experiments: list[ScannedExperiment] = field(default_factory=list)
    applied_filters: Filters | None = None

    selected_experiment: ScannedExperiment | None = field(default=None)

    skip_invalid_runs: bool = True

    @classmethod
    def create(cls, db_path: str | None = None) -> ExperimentLoader:
        """Create a loader and immediately populate it from the database."""
        resolved = db_path or str(paths.experiments_db)
        loader = cls(db_path=resolved)
        loader.refresh()
        return loader

    def refresh(self) -> None:
        """Reload all experiment metadata from DuckDB.

        Replaces `scanned_experiments` in place. Also updates `selected_experiment` to the
        freshly-loaded version so that tag edits are reflected immediately.
        """
        if not Path(self.db_path).exists():
            logger.warning(
                "DuckDB file not found — experiment list will be empty", path=self.db_path
            )
            self.scanned_experiments = []
            return

        with self.connection().session as session:
            statement = select(ScannedExperiment)
            if self.skip_invalid_runs:
                statement = statement.where(ScannedExperiment.is_wandb_valid == True)  # noqa: E712
            self.scanned_experiments = list(session.exec(statement).all())
            self.filtered_experiments = []

        logger.info(
            "Loaded experiments from DB", count=len(self.scanned_experiments), db=self.db_path
        )

        # Keep selected_experiment in sync with freshly-loaded data
        if self.selected_experiment is not None:
            by_name = {exp.experiment_name: exp for exp in self.scanned_experiments}
            self.selected_experiment = by_name.get(self.selected_experiment.experiment_name)

    def load_experiment_record(self, experiment_name: str) -> ExperimentRecord | None:
        """Load the full ``ExperimentRecord`` by reading raw player JSON files from disk.

        Returns ``None`` if the experiment is not found or has no associated files.
        """
        with self.connection().session as session:
            exp = session.exec(
                select(ScannedExperiment).where(
                    ScannedExperiment.experiment_name == experiment_name
                )
            ).one_or_none()

        if not exp or not exp.file_path_strings:
            logger.warning("No experiment files found in DB", experiment_name=experiment_name)
            return None

        player_records: list[ExperimentPlayerRecord] = [
            ExperimentPlayerRecord.model_validate_json(Path(fp).read_text())
            for fp in exp.file_path_strings
        ]
        records = build_experiment_records_from_player_records(player_records)
        return records[0] if records else None

    def save_tags(self, experiment_name: str, tags: list[str]) -> None:
        """Persist tag changes for an experiment to DuckDB and update in-memory state."""
        with self.connection().session as session:
            exp = session.get(ScannedExperiment, experiment_name)
            if exp:
                exp.tags = tags
                session.add(exp)
                session.commit()

        # Mirror change in memory so the UI reflects it without a full refresh
        for exp in self.scanned_experiments:
            if exp.experiment_name == experiment_name:
                exp.tags = tags
                break
        if (
            self.selected_experiment is not None
            and self.selected_experiment.experiment_name == experiment_name
        ):
            self.selected_experiment.tags = tags

    @property
    def all_tags(self) -> set[str]:
        """All unique tags across all loaded experiments."""
        tags: set[str] = set()
        for exp in self.scanned_experiments:
            tags.update(exp.tags or [])
        return tags

    @property
    def db_exists(self) -> bool:
        """True if the DuckDB file is present on disk."""
        return Path(self.db_path).exists()

    def connection(self) -> DuckDBConnection:
        """Get a DuckDB connection context manager for executing queries."""
        return st.connection("experiments", type=DuckDBConnection, db_path=self.db_path)
