from dataclasses import dataclass, field
from typing import Self

import streamlit as st
import structlog

from gptnt.app.loader import ExperimentLoader
from gptnt.records.models import ExperimentRecord

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
    def create(cls) -> Self:
        """Create a new state instance pre-populated from the DuckDB database."""
        loader = ExperimentLoader.create()
        return cls(loader=loader)

    def load_selected_experiment(self) -> ExperimentRecord | None:
        """Load the full ExperimentRecord for the currently selected experiment.

        Returns:
            Loaded experiment record or None if nothing is selected / not found.
        """
        if not self.loader.selected_experiment:
            logger.warning("No experiment selected")
            return None

        selected = self.loader.selected_experiment
        logger.info("Loading experiment from DB", name=selected.attempt_name)

        record = self.loader.load_experiment_record(self.loader.selected_experiment)
        self.loaded_experiment = record
        if record:
            logger.info(
                "Loaded experiment",
                session_id=record.experiment_descriptor.session_id,
                num_steps=len(record.step_records),
            )
        return record


def get_state() -> AppState:
    """Get or create the application state from Streamlit session.

    This is the primary entry point for accessing state in UI components.
    """
    if "app_state" not in st.session_state:
        st.session_state.app_state = AppState.create()

    return st.session_state.app_state
