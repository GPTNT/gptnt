import st_tailwind as tw
import streamlit as st

from gptnt.app.app_state import get_state
from gptnt.app.components.db import render_db_status
from gptnt.app.components.filters import load_options_for_filters, render_filters
from gptnt.app.extractor.view import render_extractor_view

_ = tw.initialize_tailwind()


def extractor_page() -> None:
    """Descriptive statistics grabbing for the data."""
    state = get_state()

    _ = st.header("Get statistics")
    _ = st.caption(
        "Pick one or more fields (one per line) and extract them in a single pass across all files."
    )

    with st.sidebar:
        render_db_status(state.loader)
        _ = st.divider()

    options = load_options_for_filters(state.loader.connection())
    filters = render_filters(options, expanded=False)
    render_extractor_view(state.loader.connection(), filters)
