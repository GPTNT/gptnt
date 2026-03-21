from dataclasses import dataclass

import streamlit as st


@dataclass
class PaginationState:
    """Pagination information for the current view state."""

    total_items: int
    current_page: int
    total_pages: int
    start_idx: int
    end_idx: int

    @property
    def has_prev(self) -> bool:
        """Whether there is a previous page."""
        return self.current_page > 0

    @property
    def has_next(self) -> bool:
        """Whether there is a next page."""
        return self.current_page < self.total_pages - 1


def get_pagination_state(state_key: str, total_items: int, page_size: int) -> PaginationState:
    """Initialize and get current pagination state."""
    if state_key not in st.session_state:
        st.session_state[state_key] = 0

    total_pages = (total_items + page_size - 1) // page_size
    current_page = st.session_state[state_key]

    # Ensure current page is valid
    if current_page >= total_pages:
        current_page = max(0, total_pages - 1)
        st.session_state[state_key] = current_page

    start_idx = current_page * page_size
    end_idx = min(start_idx + page_size, total_items)

    return PaginationState(
        current_page=current_page,
        total_pages=total_pages,
        start_idx=start_idx,
        end_idx=end_idx,
        total_items=total_items,
    )


@st.fragment
def render_pagination_controls(
    pagination: PaginationState, state_key: str, render_key: str | None = None
) -> None:
    """Render pagination controls (prev/next buttons)."""
    if pagination.total_pages <= 1:
        return

    key_prefix = render_key or state_key
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
            disabled=not pagination.has_prev,
            key=f"{key_prefix}_prev",
            type="tertiary",
            width="content",
        ):
            st.session_state[state_key] -= 1
            st.rerun()

        if st.button(
            "Next",
            icon=":material/chevron_forward:",
            icon_position="right",
            disabled=not pagination.has_next,
            key=f"{key_prefix}_next",
            type="tertiary",
            width="content",
        ):
            st.session_state[state_key] += 1
            st.rerun()
