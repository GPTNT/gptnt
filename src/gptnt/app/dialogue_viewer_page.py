import st_tailwind as tw
import streamlit as st

from gptnt.app.app_state import get_state
from gptnt.app.dialogue.experiment_summary import (
    render_experiment_summary_header,
    render_player_cards,
)
from gptnt.app.dialogue.view import render_dialogue_view
from gptnt.app.experiment_loader.experiment_selector import render_experiment_card


def dialogue_viewer_page() -> None:
    """Main page for viewing individual experiment dialogues."""
    _ = st.header("Dialogue Viewer")

    # Initialize state
    state = get_state()

    with st.sidebar:
        if not state.loader.selected_experiment:
            _ = st.error(
                "No experiment selected. Please select an experiment from the Experiment Loader page."
            )
            st.stop()

    with st.sidebar:
        user = st.text_input(
            "Name",
            placeholder="Your name here",
            help="Enter your name to enable saving annotations.",
        )
        state.user = user.lower().strip().replace(" ", "") if user else None

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

        save_button = st.button(
            "Save annotations",
            icon=":material/save:",
            disabled=not state.user,
            help=None
            if state.user
            else "You must enter your name above to enable saving annotations.",
        )

        if save_button and new_tags != state.loader.selected_experiment.tags:
            state.loader.save_tags(state.loader.selected_experiment.experiment_name, new_tags)

    with tw.container(classes="max-w-3xl"):
        render_player_cards(state.loaded_experiment)
        render_dialogue_view(state.loaded_experiment.step_records)
