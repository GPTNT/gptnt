from pathlib import Path

import streamlit as st

from gptnt.app.experiment_loader.state import ExperimentLoader


def render_db_status(loader: ExperimentLoader) -> None:
    """Render a compact database status block with a refresh button."""
    db_label = Path(loader.db_path).name

    if loader.db_exists:
        _ = st.caption(
            f":material/database: **{db_label}** — {len(loader.scanned_experiments)} experiments"
        )
    else:
        _ = st.warning(
            f"Database not found: `{loader.db_path}`\n\n"
            "Run `gptnt db import <directory>` to build it.",
            icon=":material/database:",
        )

    if st.button(
        ":material/refresh: Refresh",
        help="Reload experiment metadata from the database.",
        disabled=not loader.db_exists,
        width="stretch",
    ):
        loader.refresh()
        st.rerun()
