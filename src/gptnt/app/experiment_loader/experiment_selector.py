from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from streamlit.runtime.state import WidgetCallback

    from gptnt.app.experiment_loader.scanner import ScannedExperiment

PAGE_SIZE = 50
PAGINATION_STATE_KEY = "exp_selector_page"

STREAMLIT_RED = "#BD4043"


@dataclass
class PaginationState:
    """State for paginated experiment display."""

    current_page: int
    total_pages: int
    start_idx: int
    end_idx: int
    total_items: int


def get_pagination_state(total_experiments: int) -> PaginationState:
    """Initialize and get current pagination state."""
    if PAGINATION_STATE_KEY not in st.session_state:
        st.session_state[PAGINATION_STATE_KEY] = 0

    total_pages = (total_experiments + PAGE_SIZE - 1) // PAGE_SIZE
    current_page = st.session_state[PAGINATION_STATE_KEY]

    # Ensure current page is valid
    if current_page >= total_pages:
        current_page = max(0, total_pages - 1)
        st.session_state[PAGINATION_STATE_KEY] = current_page

    start_idx = current_page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_experiments)

    return PaginationState(
        current_page=current_page,
        total_pages=total_pages,
        start_idx=start_idx,
        end_idx=end_idx,
        total_items=total_experiments,
    )


@st.fragment
def render_pagination_controls(pagination: PaginationState) -> None:
    """Render pagination controls (prev/next buttons)."""
    if pagination.total_pages <= 1:
        return
    with st.container(
        horizontal=True, gap="xsmall", vertical_alignment="center", width="content", border=True
    ):
        _ = st.caption(
            f"{pagination.start_idx + 1}-{pagination.end_idx} of {pagination.total_items}",
            width="content",
        )
        if st.button(
            "Prev",
            icon=":material/chevron_backward:",
            disabled=pagination.current_page == 0,
            key="exp_prev",
            type="tertiary",
            width="content",
        ):
            st.session_state[PAGINATION_STATE_KEY] -= 1
            st.rerun()

        if st.button(
            "Next",
            icon=":material/chevron_forward:",
            icon_position="right",
            disabled=pagination.current_page >= pagination.total_pages - 1,
            key="exp_next",
            type="tertiary",
            width="content",
        ):
            st.session_state[PAGINATION_STATE_KEY] += 1
            st.rerun()


def render_experiment_card(  # noqa: WPS231
    experiment: ScannedExperiment,
    button_callback: WidgetCallback | None = None,
    idx: int | None = None,
    *,
    show_button: bool = True,
) -> ScannedExperiment | None:
    """Render a single experiment card with selection button."""
    with st.container(gap=None, horizontal=True, height="stretch", border=True, width=350):
        with st.container(gap=None, width=30, height="stretch", vertical_alignment="distribute"):
            if idx is not None:
                _ = st.markdown(f":gray[:small[#{idx + 1}]]")
                _ = st.space(size="stretch")

        with st.container(gap=None, height="stretch"):
            with st.container(horizontal=True, gap="small", width="content"):
                defuser_name = experiment.defuser or ""
                if experiment.defuser_has_manual:
                    defuser_name = f"{defuser_name}+:material/book_2:"
                _ = st.markdown(f":small[Defuser: **{defuser_name}**]")
                _ = st.markdown(f":small[Expert: **{experiment.expert or ''}**]")
            with st.container(horizontal=True, gap=None, width="content"):
                _ = st.markdown(f":small[Modules: **{', '.join(experiment.modules or [])}**]")
            for tag in experiment.tags or []:
                _ = st.badge(tag, color="red")
            with st.container(gap="xsmall", horizontal=True):
                _ = st.markdown(
                    f":small[:violet[:material/record_voice_over: {(experiment.communication_style or '').title()}]]",
                    width="content",
                )
                _ = st.markdown(
                    f":small[:green[:material/potted_plant: {experiment.seed}]]", width="content"
                )
                _ = st.markdown(
                    f":small[:blue[:material/crossword: {experiment.num_modules_solved}/{len(experiment.modules or [])}]]",
                    width="content",
                )
                timer_color = "#0891B2"
                timer_icon = ":material/timer:"
                if experiment.timer_seconds <= 0:
                    timer_color = STREAMLIT_RED
                    timer_icon = ":material/alarm:"
                _ = st.markdown(
                    f'<span style="color: {timer_color};">:small[{timer_icon} {experiment.timer_seconds:.1f}s]</span>',
                    unsafe_allow_html=True,
                    width="content",
                )
                strike_color = "#F59E0B"
                if experiment.strike_count >= 3:  # noqa: PLR2004
                    strike_color = STREAMLIT_RED
                _ = st.markdown(
                    f'<span style="color: {strike_color};">:small[:material/dangerous: {experiment.strike_count}]</span>',
                    unsafe_allow_html=True,
                    width="content",
                )
                if experiment.is_solved:
                    _ = st.markdown(":small[:green[:material/celebration:]]")
                if experiment.is_detonated:
                    _ = st.markdown(":small[:red[:material/destruction:]]")

        if show_button:
            with st.container(
                gap=None, width=20, height="stretch", vertical_alignment="distribute"
            ):
                button = st.button(
                    "",
                    key=f"select_{experiment.experiment_name}",
                    icon=":material/play_circle:",
                    type="tertiary",
                    on_click=button_callback,
                    args=(experiment,) if button_callback else None,
                )

            if button:
                return experiment

    return None


@st.cache_data
def _sort_and_index_experiments(
    experiments: list[ScannedExperiment],
) -> list[tuple[int, ScannedExperiment]]:
    """Sort experiments by name and index them."""
    sorted_experiments = sorted(experiments, key=lambda exp: exp.experiment_name)
    return list(enumerate(sorted_experiments))


def render_experiment_selector(
    scanned_experiments: list[ScannedExperiment], button_callback: WidgetCallback | None = None
) -> None:
    """Render experiment selector with detailed metadata and pagination.

    Shows scanned experiments and allows selection before loading.
    """
    if not scanned_experiments:
        _ = st.info("No experiments to show.")
        return

    # Sort by name for consistent display
    indexed_experiments = _sort_and_index_experiments(scanned_experiments)

    # Get pagination state
    pagination = get_pagination_state(len(indexed_experiments))
    page_experiments = indexed_experiments[pagination.start_idx : pagination.end_idx]

    with st.container(horizontal=True):
        for idx, experiment in page_experiments:
            _ = render_experiment_card(experiment, button_callback=button_callback, idx=idx)
