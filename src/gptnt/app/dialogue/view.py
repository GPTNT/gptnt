from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

from gptnt.app.dialogue.components import (
    render_dialogue_bubble,
    render_display_controls,
    render_pagination_controls,
)
from gptnt.app.dialogue.data import build_step_viewmodels
from gptnt.app.dialogue.state import DialogueState

if TYPE_CHECKING:
    from gptnt.players.metrics.records import ExperimentStepRecord


def render_dialogue_view(step_records: list[ExperimentStepRecord]) -> None:
    """Render the full dialogue view with display controls and pagination.

    This is the main entry point for the dialogue viewer. It handles:
    - State initialization and management
    - Display control rendering
    - View model creation
    - Pagination calculation
    - Dialogue bubble rendering
    """
    # 1. Get or create state
    state = DialogueState.get_or_create()

    # 2. Render display controls and capture changes
    output_format, message_display, new_page_size = render_display_controls(state)

    # 3. Handle page size changes (triggers rerun)
    if new_page_size != state.page_size:
        state.set_page_size(new_page_size)
        # set_page_size calls st.rerun(), so code below won't execute
        return

    # 4. Build view models (pre-compute all display data)
    viewmodels = build_step_viewmodels(step_records)

    # 5. Calculate pagination
    pagination = state.get_pagination_info(len(viewmodels))

    # 6. Render top pagination controls
    render_pagination_controls(pagination, state, "top")

    # 7. Render dialogue bubbles
    with st.container(border=True):
        for vm in viewmodels[pagination.start_idx : pagination.end_idx]:
            render_dialogue_bubble(
                vm,
                render_as_raw=output_format == "Raw",
                force_collapsed=message_display == "Folded",
            )

    # 8. Render bottom pagination controls
    render_pagination_controls(pagination, state, "bottom")
