import streamlit as st

from gptnt.app.loader import ExperimentLoader


def render_db_status(loader: ExperimentLoader) -> None:
    """Render a compact database status block with a refresh button."""
    db_label = loader.db_path.name
    if loader.db_exists:
        _ = st.caption(f":material/database: **{db_label}**", help=f"Path: {loader.db_path}")
    else:
        _ = st.warning(
            f"Database not found: `{loader.db_path}`\n\n"
            "Run `gptnt db import <directory>` to build it.",
            icon=":material/database:",
        )
        st.stop()

    skip_invalid_runs = st.toggle(
        ":small[Hide invalid runs]",
        value=loader.skip_invalid_runs,
        help="This will exclude all the old or failed or invalid runs from WandB.",
    )

    count = loader.count_experiments(skip_invalid=skip_invalid_runs)
    _ = st.caption(f":small[:gray[{count:,} experiments]]")

    button_type = "primary" if skip_invalid_runs != loader.skip_invalid_runs else "secondary"  # noqa: WPS504
    refresh_button = st.button(
        ":material/refresh: Refresh",
        help="Reload experiment metadata from the database.",
        disabled=not loader.db_exists and skip_invalid_runs != loader.skip_invalid_runs,
        width="stretch",
        type=button_type,
    )

    if refresh_button:
        loader.skip_invalid_runs = skip_invalid_runs
        st.rerun()
