import st_tailwind as tw
import streamlit as st

from gptnt.app.app_state import get_state
from gptnt.app.components.filter_pills import render_filter_pills
from gptnt.app.dialogue.view import render_experiment
from gptnt.app.experiment_loader.components import (
    render_directory_selector,
    render_scan_experiments_controls,
    render_wandb_configuration,
)
from gptnt.app.experiment_loader.experiment_selector import render_experiment_selector
from gptnt.app.experiment_loader.filters import apply_filters, get_filter_options


def dialogue_viewer_page() -> None:
    """Main page for viewing individual experiment dialogues."""
    _ = st.header("💣 KTANE Dialogue Viewer")

    # Initialize state
    state = get_state()

    with st.sidebar:
        directory = render_directory_selector(state.loader)
        render_wandb_configuration(state.loader)
        render_scan_experiments_controls(
            loader=state.loader, directory=directory, wandb_path=state.loader.wandb_path
        )

        # Show filter controls if we have scanned experiments
        if state.loader.scanned_experiments:
            options = get_filter_options(state.loader.scanned_experiments)
            filters = render_filter_pills(options)
            filtered_experiments = state.loader.scanned_experiments

            # Apply filters and show results
            if filters:
                filtered_experiments = apply_filters(state.loader.scanned_experiments, filters)

            selected_experiment = render_experiment_selector(filtered_experiments)
            if selected_experiment:
                state.loader.selected_experiment = selected_experiment

    if not state.loader.selected_experiment:
        st.stop()

    with st.sidebar:
        _ = st.divider()
        if st.button(
            ":material/open_in_browser:&nbsp;&nbsp;Load Experiment",
            type="primary",
            width="stretch",
        ):
            with st.spinner("Loading experiment files..."):
                _ = state.load_selected_experiment()
            st.rerun()

    if not state.loaded_experiment:
        with tw.container(classes="max-w-3xl"):
            _ = st.info("👆 Click 'Load Experiment' to view the dialogue")
        st.stop()

    with tw.container(classes="max-w-3xl"):
        render_experiment(state.loaded_experiment)
