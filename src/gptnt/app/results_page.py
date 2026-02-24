from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

import st_tailwind as tw
import streamlit as st

from gptnt.app.app_state import get_state
from gptnt.app.components.filter_pills import render_filter_pills
from gptnt.app.experiment_loader.components import (
    render_directory_selector,
    render_scan_experiments_controls,
    render_wandb_configuration,
)
from gptnt.app.experiment_loader.filters import apply_filters, get_filter_options
from gptnt.app.experiment_loader.lightweight_loader import load_all_experiments_lightweight
from gptnt.app.results_data import build_results_dataframe

if TYPE_CHECKING:
    from gptnt.players.metrics.records import ExperimentRecord


def _experiment_base_name(name: str) -> str:
    """Strip the trailing session UUID from a full experiment name."""
    paren_pos = name.rfind(")")
    if paren_pos == -1:
        return name
    return name[: paren_pos + 1]


def _apply_name_filter(
    experiments: list[ExperimentRecord], allowed_names: set[str]
) -> list[ExperimentRecord]:
    """Return only experiment records whose base name is in *allowed_names*."""
    return [
        exp
        for exp in experiments
        if _experiment_base_name(exp.experiment_descriptor.name) in allowed_names
    ]


def results_page() -> None:  # noqa: WPS210
    """Render a results page for all the runs."""
    _ = st.header(":material/analytics: Experiment Results")

    # Initialize state
    state = get_state()

    with st.sidebar:
        directory = render_directory_selector(state.loader)
        render_wandb_configuration(state.loader)
        render_scan_experiments_controls(
            loader=state.loader, directory=directory, wandb_path=state.loader.wandb_path
        )

    if not state.loader.scanned_experiments:
        with tw.container(classes="max-w-5xl"):
            _ = st.info(
                ":material/feature_search: Scan an experiment directory from the sidebar to get started."
            )
        st.stop()

    # Filter controls live in the sidebar
    with st.sidebar:
        options = get_filter_options(state.loader.scanned_experiments)
        filters = render_filter_pills(options)
        filtered_experiments = apply_filters(state.loader.scanned_experiments, filters)
        _ = st.caption(
            f":small[{len(filtered_experiments)} / {len(state.loader.scanned_experiments)} experiments]"
        )

    with tw.container(classes="max-w-5xl"):
        col_load, col_info = st.columns([2, 3], gap="medium")

        with col_load:
            load_clicked = st.button(
                ":material/table_view:&nbsp;&nbsp;Load All Results",
                type="primary",
                width="stretch",
            )
            if load_clicked:
                st.session_state.results_loaded = True

        if not st.session_state.get("results_loaded"):
            with col_info:
                _ = st.caption(
                    ":small[Click **Load All Results** to build the summary table. "
                    "Observations and messages are skipped for speed.]"
                )
            st.stop()

        # Load ALL scanned experiments (not just filtered) so the cache stays warm
        # when the user adjusts filters. Filtering is applied to the DataFrame instead.
        with st.spinner("Loading experiment records…"):
            all_experiments = load_all_experiments_lightweight(state.loader.scanned_experiments)

        # Determine which experiment names survive the current filter
        filtered_names = {exp.experiment_name for exp in filtered_experiments}
        has_active_filter = filters and any(bool(fv) for fv in asdict(filters).values())
        visible_experiments = (
            _apply_name_filter(all_experiments, filtered_names)
            if has_active_filter
            else all_experiments
        )

        _ = st.caption(
            f":small[Showing **{len(visible_experiments)}** of **{len(all_experiments)}** loaded records]"
        )

        if not visible_experiments:
            _ = st.warning("No experiments match the current filters.")
            st.stop()

        df = build_results_dataframe(visible_experiments)
        _ = st.dataframe(df, width="stretch", hide_index=True)
