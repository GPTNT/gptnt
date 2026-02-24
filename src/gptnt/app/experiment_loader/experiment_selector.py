from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import streamlit as st
from caseconverter import titlecase

if TYPE_CHECKING:
    from gptnt.app.experiment_loader.scanner import ScannedExperiment


PAGE_SIZE = 10
PAGINATION_STATE_KEY = "exp_selector_page"


@dataclass
class PaginationState:
    """State for paginated experiment display."""

    current_page: int
    total_pages: int
    start_idx: int
    end_idx: int
    total_items: int


def _get_pagination_state(total_experiments: int) -> PaginationState:
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


def _render_pagination_controls(pagination: PaginationState, position: str) -> None:
    """Render pagination controls (prev/next buttons).

    Args:
        pagination: Current pagination state
        position: Either "top" or "btm" for unique button keys
    """
    if pagination.total_pages <= 1:
        return

    nav_cols = st.columns([1, 2, 1])

    with nav_cols[0]:
        if st.button(
            ":material/chevron_backward: Prev",
            disabled=pagination.current_page == 0,
            key=f"exp_prev_{position}",
        ):
            st.session_state[PAGINATION_STATE_KEY] -= 1
            st.rerun()

    with nav_cols[1]:
        if position == "top":
            _ = st.caption(
                f"Showing {pagination.start_idx + 1}-{pagination.end_idx} of {pagination.total_items}"
            )
        else:
            _ = st.caption(f"Page {pagination.current_page + 1} of {pagination.total_pages}")

    with nav_cols[2]:
        if st.button(
            "Next :material/chevron_forward:",
            disabled=pagination.current_page >= pagination.total_pages - 1,
            key=f"exp_next_{position}",
        ):
            st.session_state[PAGINATION_STATE_KEY] += 1
            st.rerun()


def _render_experiment_card(
    experiment: ScannedExperiment, card_index: int
) -> ScannedExperiment | None:
    """Render a single experiment card with selection button."""
    with st.container(gap=None):
        # Header row with pairing and index
        left, right = st.columns([3, 1], gap=None)
        with left, st.container(horizontal=True, gap=None):
            _ = st.markdown(f":small[Defuser: **{experiment.defuser}**]")
            _ = st.markdown(f":small[Expert: **{experiment.expert}**]")
        with right, st.container(horizontal=True, gap=None):
            _ = st.caption(f"#{card_index}", text_alignment="right")

        # Modules list
        _ = st.markdown(f":small[Modules: **{', '.join(experiment.modules)}**]")

        _ = st.space(size="xsmall")

        # Metadata badges
        _ = st.markdown(
            f":violet-badge[{titlecase(experiment.condition)}] "
            f":blue-badge[{titlecase(experiment.communication_style)}] "
            # f":green-badge[{len(experiment.modules)} modules] "
            f":orange-badge[Seed: {experiment.seed}]"
        )

        _ = st.space(size="xsmall")

        with st.container(gap=None, horizontal=True):
            _ = st.markdown(
                f":small[:gray[:material/timer: {experiment.bomb_state.timer_module.seconds_remaining:.1f}s]]",
                width="content",
            )
            _ = st.space(size="xsmall")
            _ = st.markdown(
                f":small[:orange[:material/dangerous: {len(experiment.bomb_state.strikes) if experiment.bomb_state.strikes else 0}]]",
                width="content",
            )
            _ = st.space(size="xsmall")

            if experiment.bomb_state.is_solved:
                _ = st.markdown(":small[:green[:material/celebration:]]", width="content")
            if experiment.bomb_state.is_detonated:
                _ = st.markdown(":small[:red[:material/destruction:]]", width="content")
            _ = st.space(size="stretch")

        _ = st.space(size="small")

        with st.expander(":small[Last Bomb State]"):
            _ = st.json(experiment.bomb_state.model_dump(mode="json"))

        # Selection button
        _ = st.space(size="small")
        if st.button("Select", key=f"select_{experiment.experiment_name}", width="stretch"):
            return experiment

    return None


def render_experiment_selector(
    scanned_experiments: list[ScannedExperiment],
) -> ScannedExperiment | None:
    """Render experiment selector with detailed metadata and pagination.

    Shows scanned experiments and allows selection before loading.
    """
    if not scanned_experiments:
        _ = st.info("No experiments to show.")
        return None

    # Sort by name for consistent display
    sorted_experiments = sorted(scanned_experiments, key=lambda exp: exp.experiment_name)

    # Get pagination state
    pagination = _get_pagination_state(len(sorted_experiments))
    page_experiments = sorted_experiments[pagination.start_idx : pagination.end_idx]

    with st.expander(
        f"Available Experiments ({pagination.total_items}) - "
        f"Page {pagination.current_page + 1}/{pagination.total_pages}",
        expanded=False,
    ):
        # Top pagination controls
        _render_pagination_controls(pagination, position="top")

        # Render experiment cards
        for idx, experiment in enumerate(page_experiments):
            selected = _render_experiment_card(experiment, idx)
            if selected:
                return selected

            # Add divider between cards (except after last card)
            if idx < len(page_experiments) - 1:
                _ = st.divider()

        # Bottom pagination controls
        _render_pagination_controls(pagination, position="btm")

    return None
