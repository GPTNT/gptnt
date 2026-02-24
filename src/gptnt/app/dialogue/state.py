"""State management layer for dialogue view.

This module manages all UI state for the dialogue viewer, including pagination, display options,
and navigation.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

DIALOGUE_STATE_SESSION_KEY = "dialogue_state"

PAGE_SIZE_OPTIONS = (10, 20, 50, 100)


@dataclass
class PaginationInfo:
    """Pagination information for the current view state."""

    total_items: int
    current_page: int
    page_size: int
    total_pages: int
    start_idx: int
    end_idx: int
    has_prev: bool
    has_next: bool


@dataclass
class DialogueState:
    """State manager for dialogue view."""

    page: int = 0
    page_size: int = 20
    output_format: str = "Pretty"
    message_display: str = "Expanded"

    @classmethod
    def get_or_create(cls) -> DialogueState:
        """Get existing state from session or create new one.

        Returns:
            DialogueState instance
        """
        if DIALOGUE_STATE_SESSION_KEY not in st.session_state:
            st.session_state[DIALOGUE_STATE_SESSION_KEY] = cls()
        return st.session_state[DIALOGUE_STATE_SESSION_KEY]

    def save(self) -> None:
        """Save state back to session."""
        st.session_state[DIALOGUE_STATE_SESSION_KEY] = self

    def get_pagination_info(self, total_items: int) -> PaginationInfo:
        """Calculate pagination information.

        Args:
            total_items: Total number of items to paginate

        Returns:
            PaginationInfo with computed pagination values
        """
        if total_items == 0:
            return PaginationInfo(
                total_items=0,
                current_page=0,
                page_size=self.page_size,
                total_pages=0,
                start_idx=0,
                end_idx=0,
                has_prev=False,
                has_next=False,
            )

        total_pages = (total_items + self.page_size - 1) // self.page_size

        # Ensure current page is valid
        current_page = min(self.page, total_pages - 1)
        current_page = max(0, current_page)

        # Update state if page was adjusted
        if current_page != self.page:
            self.page = current_page
            self.save()

        start_idx = current_page * self.page_size
        end_idx = min(start_idx + self.page_size, total_items)

        return PaginationInfo(
            total_items=total_items,
            current_page=current_page,
            page_size=self.page_size,
            total_pages=total_pages,
            start_idx=start_idx,
            end_idx=end_idx,
            has_prev=current_page > 0,
            has_next=current_page < total_pages - 1,
        )

    def go_prev(self) -> None:
        """Navigate to previous page."""
        if self.page > 0:
            self.page -= 1
            self.save()
            st.rerun()

    def go_next(self, total_pages: int) -> None:
        """Navigate to next page.

        Args:
            total_pages: Total number of pages
        """
        if self.page < total_pages - 1:
            self.page += 1
            self.save()
            st.rerun()

    def set_page_size(self, size: int) -> None:  # noqa: WPS615
        """Set page size and reset to first page."""
        if size != self.page_size:
            self.page_size = size
            self.page = 0
            self.save()
            st.rerun()
