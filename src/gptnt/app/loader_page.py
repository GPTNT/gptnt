import pandas as pd
import st_tailwind as tw
import streamlit as st
from more_itertools import collapse
from sqlmodel import select

from gptnt.app.app_state import get_state
from gptnt.app.components.filters import Filters, apply_filters, render_filters
from gptnt.app.experiment_loader.components import render_db_status
from gptnt.app.experiment_loader.experiment_selector import (
    get_pagination_state,
    render_experiment_card,
    render_experiment_selector,
    render_pagination_controls,
)
from gptnt.app.experiment_loader.scanner import ScannedExperiment

_ = tw.initialize_tailwind()


def _select_callback(experiment: ScannedExperiment) -> None:
    state = get_state()
    state.loader.selected_experiment = experiment
    if state.loaded_experiment:
        state.loaded_experiment = None
    _ = st.toast(f"Selected experiment: {experiment.experiment_name}")


@st.cache_data()
def load_options_for_filters() -> Filters:
    """Load the options for the filters from the database."""
    state = get_state()
    with state.loader.connection().session as session:
        options = Filters(
            condition=session.exec(select(ScannedExperiment.condition).distinct()).all(),
            communication_style=session.exec(
                select(ScannedExperiment.communication_style).distinct()
            ).all(),
            modules=list(
                set(collapse(session.exec(select(ScannedExperiment.modules).distinct()).all()))
            ),
            defuser=session.exec(select(ScannedExperiment.defuser).distinct()).all(),
            expert=session.exec(select(ScannedExperiment.expert).distinct()).all(),
            seed=session.exec(select(ScannedExperiment.seed).distinct()).all(),
            experiment_name=session.exec(
                select(ScannedExperiment.experiment_name).distinct()
            ).all(),
        )
    return options


def render_experiment_browser(
    experiments_to_render: list[ScannedExperiment], entry_render_format: str
) -> None:
    """Render the experiment selection browser."""
    if len(experiments_to_render) > 200:  # noqa: PLR2004
        _ = st.warning(
            f"Too many experiments to display ({len(experiments_to_render)}). "
            "Apply more filters to narrow down the results."
        )

    match entry_render_format:
        case "Cards":
            _ = render_experiment_selector(experiments_to_render, button_callback=_select_callback)
        case "Table":
            df = pd.DataFrame(
                [
                    {
                        "experiment": entry.experiment_name,
                        "condition": entry.condition,
                        "style": entry.communication_style,
                        "modules": ", ".join(entry.modules) if entry.modules else "",
                        "seed": entry.seed,
                        "defuser": entry.defuser,
                        "expert": entry.expert,
                        "end_state": entry.end_state,
                        "timer": entry.timer_seconds,
                        "strikes": entry.strike_count,
                        "wandb_valid": entry.is_wandb_valid,
                    }
                    for entry in experiments_to_render
                ]
            )
            _ = st.dataframe(df)
        case _:
            _ = st.error("Unsupported render format selected.")


def loader_page() -> None:
    """Browse and select experiments from the DuckDB database."""
    _ = st.header("Experiment Loader")

    state = get_state()

    with st.sidebar:
        render_db_status(state.loader)
        _ = st.divider()

    if not state.loader.db_exists:
        st.stop()

    with st.sidebar:
        if state.loader.selected_experiment:
            _ = st.subheader("Selected Experiment")
            _ = st.caption("*Go to the Dialogue Viewer page to load the experiment.*")
            _ = render_experiment_card(state.loader.selected_experiment, show_button=False)

    experiments_to_render = state.loader.scanned_experiments

    with st.container(horizontal=True):
        entry_render_format = st.segmented_control(
            "Render Format", options=["Cards", "Table"], default="Cards"
        )
        if not entry_render_format:
            _ = st.error("Please select a render format.")
            st.stop()
        _ = st.space("stretch")
        pagination_state = get_pagination_state(len(experiments_to_render))
        render_pagination_controls(pagination_state)

    options = load_options_for_filters()
    filters = render_filters(options, expanded=False)

    if experiments_to_render:
        experiments_to_render = apply_filters(experiments_to_render, filters)
        render_experiment_browser(experiments_to_render, entry_render_format)
