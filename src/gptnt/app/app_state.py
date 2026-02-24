from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import streamlit as st
import structlog

from gptnt.app.experiment_loader.state import ExperimentLoader
from gptnt.players.metrics.records import (
    ExperimentPlayerRecord,
    build_experiment_records_from_player_records,
)

if TYPE_CHECKING:
    from gptnt.players.metrics.records import ExperimentRecord

logger = structlog.get_logger()


@dataclass
class AppState:
    """Main application state coordinator.

    The state is designed to survive Streamlit reruns when stored in st.session_state.
    """

    # Subsystems
    loader: ExperimentLoader

    # Loaded data
    loaded_experiment: ExperimentRecord | None = field(default=None, init=False)

    @classmethod
    def create(cls) -> AppState:
        """Create a new state instance with the given data directory.

        Args:
            data_directory: Path to directory containing experiment JSON files

        Returns:
            Initialized state instance
        """
        loader = ExperimentLoader()
        return cls(loader=loader)

    def reset(self) -> None:
        """Reset the state to initial conditions."""
        self.loader = ExperimentLoader()
        self.loaded_experiment = None

    def load_selected_experiment(self) -> ExperimentRecord | None:
        """Load player records from selected experiment and merge into ExperimentRecord.

        Returns:
            Loaded experiment record or None if loading failed
        """
        if not self.loader.selected_experiment:
            logger.warning("No experiment selected")
            return None

        selected = self.loader.selected_experiment
        logger.info(
            "Loading experiment",
            experiment_name=selected.experiment_name,
            num_files=len(selected.file_paths),
        )

        # Load all player records from files
        player_records: list[ExperimentPlayerRecord] = []
        for file_path in selected.file_paths:
            record = ExperimentPlayerRecord.model_validate_json(file_path.read_text())
            player_records.append(record)

        experiment_records = build_experiment_records_from_player_records(player_records)

        # Store the first (and typically only) experiment record
        self.loaded_experiment = experiment_records[0]
        logger.info(
            "Loaded experiment",
            session_id=self.loaded_experiment.experiment_descriptor.session_id,
            num_steps=len(self.loaded_experiment.step_records),
        )

        return self.loaded_experiment


def get_state() -> AppState:
    """Get or create the application state from Streamlit session.

    This is the primary entry point for accessing state in UI components.
    """
    if "app_state" not in st.session_state:
        st.session_state.app_state = AppState.create()

    return st.session_state.app_state
