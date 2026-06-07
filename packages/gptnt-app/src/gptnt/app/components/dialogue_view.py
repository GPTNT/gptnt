from collections.abc import Iterable
from dataclasses import dataclass
from typing import Self

import streamlit as st

from gptnt.app.components.dialogue_bubble import render_dialogue_bubble
from gptnt.app.components.pagination import get_pagination_state, render_pagination_controls
from gptnt.records.models import ExperimentStepRecord

DIALOGUE_STATE_SESSION_KEY = "dialogue_state"
DIALOGUE_PAGE_SESSION_KEY = "dialogue_page"  # owned by get_pagination_state

DIALOGUE_PAGE_SIZE_OPTIONS = (10, 20, 50, 100)


@dataclass
class DialogueState:
    """State manager for dialogue view."""

    page_size: int = 20
    output_format: str = "Pretty"
    message_display: str = "Expanded"

    @classmethod
    def get_or_create(cls) -> Self:
        """Get existing state from session or create new one."""
        if DIALOGUE_STATE_SESSION_KEY not in st.session_state:
            st.session_state[DIALOGUE_STATE_SESSION_KEY] = cls()
        return st.session_state[DIALOGUE_STATE_SESSION_KEY]

    def save(self) -> None:
        """Save state back to session."""
        st.session_state[DIALOGUE_STATE_SESSION_KEY] = self

    def set_page_size(self, size: int) -> None:  # noqa: WPS615
        """Set page size and reset to first page."""
        if size != self.page_size:
            self.page_size = size
            self.save()
            st.session_state[DIALOGUE_PAGE_SESSION_KEY] = 0
            st.rerun()


def render_display_controls(
    state: DialogueState, *, page_size_options: Iterable[int] = DIALOGUE_PAGE_SIZE_OPTIONS
) -> tuple[str, str, int]:
    """Render display control selectors."""
    with st.container(horizontal=True, vertical_alignment="center"):
        output_format = st.segmented_control(
            "Output Format",
            ["Pretty", "Raw"],
            selection_mode="single",
            default=state.output_format,
        )
        _ = st.space(size="stretch")
        message_display = st.segmented_control(
            "Message Display",
            ["Expanded", "Folded"],
            selection_mode="single",
            default=state.message_display,
        )

        _ = st.space(size="stretch")
        page_size = st.segmented_control(
            "Steps per page",
            options=page_size_options,
            key="page_size_selector",
            default=state.page_size,
        )
    return output_format or "Pretty", message_display or "Expanded", page_size or state.page_size


def render_dialogue_view(step_records: list[ExperimentStepRecord]) -> None:
    """Render the full dialogue view with display controls and pagination."""
    # 1. Get or create state
    state = DialogueState.get_or_create()

    # 2. Render display controls and capture changes
    output_format, message_display, new_page_size = render_display_controls(state)

    # 3. Handle page size changes (triggers rerun)
    if new_page_size != state.page_size:
        state.set_page_size(new_page_size)
        return

    # 4. Calculate pagination directly against the records
    pagination = get_pagination_state(
        DIALOGUE_PAGE_SESSION_KEY, len(step_records), state.page_size
    )

    # 5. Render top pagination controls
    render_pagination_controls(pagination, DIALOGUE_PAGE_SESSION_KEY, render_key="dialogue_top")

    # 6. Render dialogue bubbles
    with st.container(border=True):
        for idx, step in enumerate(
            step_records[pagination.start_idx : pagination.end_idx], start=pagination.start_idx
        ):
            render_dialogue_bubble(
                step,
                idx=idx,
                render_as_raw=output_format == "Raw",
                force_collapsed=message_display == "Folded",
            )

    # 7. Render bottom pagination controls
    render_pagination_controls(pagination, DIALOGUE_PAGE_SESSION_KEY, render_key="dialogue_bottom")
