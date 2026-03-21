import streamlit as st

from gptnt.app.app_state import get_state
from gptnt.app.components.experiment_card import render_experiment_card
from gptnt.app.components.pagination import get_pagination_state
from gptnt.records.models import ExperimentMetadata

BROWSER_PAGE_SIZE = 50
BROWSER_PAGINATION_STATE_KEY = "exp_selector_page"


def _select_callback(experiment: ExperimentMetadata) -> None:
    state = get_state()
    state.loader.selected_experiment = experiment
    if state.loaded_experiment:
        state.loaded_experiment = None
    _ = st.toast(f"Selected experiment: {experiment.attempt_name}")


@st.cache_data
def _sort_and_index_experiments(
    experiments: list[ExperimentMetadata],
) -> list[tuple[int, ExperimentMetadata]]:
    """Sort experiments by name and index them."""
    sorted_experiments = sorted(experiments, key=lambda exp: exp.attempt_name)
    return list(enumerate(sorted_experiments))


def render_experiment_browser(experiments_to_render: list[ExperimentMetadata]) -> None:
    """Render the experiment selection browser."""
    if not experiments_to_render:
        _ = st.info("No experiments to show.")
        return

    if len(experiments_to_render) > 200:  # noqa: PLR2004
        _ = st.warning(
            f"Too many experiments to display ({len(experiments_to_render)}). "
            "Apply more filters to narrow down the results."
        )

    # Sort by name for consistent display
    indexed_experiments = _sort_and_index_experiments(experiments_to_render)

    # Get pagination state
    pagination = get_pagination_state(
        BROWSER_PAGINATION_STATE_KEY, len(indexed_experiments), BROWSER_PAGE_SIZE
    )
    page_experiments = indexed_experiments[pagination.start_idx : pagination.end_idx]

    with st.container(horizontal=True):
        for idx, experiment in page_experiments:
            _ = render_experiment_card(experiment, button_callback=_select_callback, idx=idx)
