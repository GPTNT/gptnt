import st_tailwind as tw
import streamlit as st
from more_itertools import collapse
from sqlmodel import select

from gptnt.app.app_state import get_state
from gptnt.app.components.browser import render_experiment_browser
from gptnt.app.components.filters import Filters, apply_filters, render_filters
from gptnt.app.dialogue.experiment_summary import (
    render_experiment_summary_header,
    render_player_cards,
)
from gptnt.app.dialogue.view import render_dialogue_view
from gptnt.app.experiment_loader.components import render_db_status
from gptnt.app.experiment_loader.experiment_selector import (
    get_pagination_state,
    render_experiment_card,
    render_pagination_controls,
    render_selector_legend,
)
from gptnt.app.experiment_loader.scanner import ScannedExperiment

_ = tw.initialize_tailwind()


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
            name=session.exec(select(ScannedExperiment.name).distinct()).all(),
            tags=list(
                set(collapse(session.exec(select(ScannedExperiment.tags).distinct()).all()))
            ),
        )
    return options


def dialogue_selector_page() -> None:
    """Browse and select experiments from the DuckDB database."""
    state = get_state()
    with st.sidebar:
        render_db_status(state.loader)
        _ = st.divider()

    with st.sidebar:
        entry_render_format = st.segmented_control(
            "Render Format", options=["Cards", "Table"], default="Cards"
        )
        if not entry_render_format:
            _ = st.error("Please select a render format.")
            st.stop()
        _ = st.space("stretch")

    options = load_options_for_filters()
    filters = render_filters(options, expanded=not bool(state.loader.filtered_experiments))

    if state.loader.filtered_experiments and filters != state.loader.applied_filters:
        state.loader.filtered_experiments = []
        st.rerun()
    with st.container(horizontal=True, vertical_alignment="center"):
        with st.container(horizontal=True, vertical_alignment="center"):
            load_button = st.button(
                "Load experiments", icon=":material/downloading:", type="primary", width="content"
            )
            if state.loader.filtered_experiments:
                _ = st.caption(
                    f"Found {len(state.loader.filtered_experiments)} experiments matching the filters."
                )
        render_selector_legend()
    with st.container(horizontal=True):
        pagination_state = get_pagination_state(len(state.loader.filtered_experiments))
        render_pagination_controls(pagination_state)

    if load_button:
        filtered = apply_filters(state.loader.scanned_experiments, filters)
        state.loader.applied_filters = filters
        if filtered:
            state.loader.filtered_experiments = filtered
        else:
            filtered = []
        st.rerun()

    if state.loader.filtered_experiments:
        render_experiment_browser(state.loader.filtered_experiments, entry_render_format)


def dialogue_viewer_page() -> None:
    """Main page for viewing individual experiment dialogues."""
    # Initialize state
    state = get_state()

    with st.sidebar:
        if not state.loader.selected_experiment:
            _ = st.error(
                "No experiment selected. Please select an experiment from the Experiment Loader page."
            )
            st.stop()

    with st.sidebar:
        if state.loader.selected_experiment:
            _ = st.subheader("Selected Experiment")
            # _ = st.caption("*Go to the Dialogue Viewer page to load the experiment.*")
            _ = render_experiment_card(state.loader.selected_experiment, show_button=False)

        if st.button(
            ":material/open_in_browser:&nbsp;&nbsp;Load Experiment",
            type="primary",
            width="stretch",
        ):
            with st.spinner("Loading experiment files..."):
                _ = state.load_selected_experiment()
            st.rerun()

    if not state.loaded_experiment:
        st.stop()

    with st.sidebar:
        render_experiment_summary_header(state.loaded_experiment)

        _ = st.divider()

        new_tags = st.multiselect(
            ":material/tag: Tags",
            options=sorted(state.loader.all_tags),
            default=state.loader.selected_experiment.tags,
            accept_new_options=True,
        )
        if "None" in new_tags:
            _ = st.error("The tag 'None' is reserved and cannot be used.")
            st.stop()

        save_button = st.button(
            "Save annotations",
            icon=":material/save:",
            disabled=state.loader.selected_experiment.tags == new_tags,
        )

        if save_button and new_tags != state.loader.selected_experiment.tags:
            state.loader.save_tags(state.loader.selected_experiment.name, new_tags)

    with tw.container(classes="max-w-3xl"):
        render_player_cards(state.loaded_experiment)
        render_dialogue_view(state.loaded_experiment.step_records)


def render_dialogue_viewer() -> None:
    """Entry point for the Dialogue Viewer page."""
    state = get_state()
    if state.loader.selected_experiment:
        reset_button = st.button(
            ":small[:material/arrow_back: Experiment Selector]", type="tertiary", width="content"
        )
        if reset_button:
            state.loader.selected_experiment = None
            st.rerun()
        dialogue_viewer_page()
    else:
        dialogue_selector_page()
