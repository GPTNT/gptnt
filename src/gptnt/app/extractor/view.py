import io

import polars as pl
import streamlit as st
from pydantic_core import to_jsonable_python
from whenever import Instant

from gptnt.app.components.filters import Filters, apply_filters
from gptnt.app.extractor.data import extract_from_step_records_db
from gptnt.app.extractor.path_validator import validate_path
from gptnt.experiments.db.connection import DuckDBConnection


def _parse_fields(raw: str) -> list[str]:
    """Parse newline-separated field paths, stripping blanks."""
    return [line.strip() for line in raw.splitlines() if line.strip()]


def render_field_input() -> tuple[list[str], bool]:
    """Render the field path input widget with real-time per-field validation.

    Returns:
        A tuple of `(fields, all_valid)` where:
        - `fields` is the parsed list of field path strings entered by the user.
        - `all_valid` is True only when at least one field is entered and all pass
          validation. Use this to gate the Extract button.
    """
    with st.container(horizontal=True, vertical_alignment="bottom"):
        with st.container():
            fields_input = st.text_area(
                "Fields to extract (one per line)",
                placeholder="bomb_state.modules[].module_name\nerror_type[]\nstep",
                height=120,
            )
            fields = _parse_fields(fields_input)

            all_valid = True
            for field in fields:
                try:
                    validate_path(field)
                except AttributeError as err:
                    all_valid = False
                    _ = st.error(f"**{field}** — {err}", icon=":material/close:")

        extract_button = st.button("Extract", disabled=not all_valid, type="primary")

    return fields, extract_button


def render_extractor_view(connection: DuckDBConnection, filters: Filters) -> None:
    """Orchestrate the full field-extraction UI (DB-backed).

    Pipeline:
        1. Render field input widget → obtain fields + button state
        2. On button press: apply filters, fetch + extract fields from the
           experiment_step_records table, build the result DataFrame
        3. Render download button and DataFrame preview
    """
    # 1. Field input + extract button
    fields, extract_button = render_field_input()

    # 2. Extraction pipeline (only runs when button is pressed)
    if not extract_button:
        return

    with st.status("Running...", expanded=True) as status:
        # 2a. Apply filters
        st.write("Applying filters...")
        filtered_experiments = apply_filters(connection, filters)

        st.write(
            f"Extracting {len(fields)} field(s) across "
            f"{len(filtered_experiments)} experiments from database..."
        )

        # 2b. Extract from DB with progress per experiment
        progress_bar = st.progress(0, text="Processing experiments…")

        def _update_progress(completed: int, total: int) -> None:  # noqa: WPS430
            fraction = completed / total if total else 1.0
            _ = progress_bar.progress(
                fraction, text=f"Processed {completed} / {total} experiments…"
            )

        extracted_data = extract_from_step_records_db(
            connection=connection,
            experiments=filtered_experiments,
            fields=fields,
            progress_callback=_update_progress,
        )

        _ = progress_bar.progress(
            1.0, text=f"Done — {len(filtered_experiments)} experiments processed."
        )

        # 2c. Build DataFrame
        st.write("Building dataframe...")
        df = pl.DataFrame(to_jsonable_python(extracted_data), infer_schema_length=None)

        status.update(
            label=f":material/grading: Extracted from {len(filtered_experiments)} experiments.",
            state="complete",
            expanded=False,
        )

    # 3. Download + preview
    with st.container(horizontal=True, vertical_alignment="center"):
        _ = st.caption("Showing up to 50 rows. Use the download button to get everything.")
        buffer = io.BytesIO()
        df.write_parquet(buffer)
        _ = buffer.seek(0)

        timestamp = Instant.now().format_common_iso().replace(":", "-")

        _ = st.download_button(
            label="Download as Parquet",
            data=buffer,
            file_name=f"results_{timestamp}.parquet",
            mime="application/octet-stream",
            type="primary",
        )
    _ = st.markdown("**Preview**")
    _ = st.dataframe(df.head(50))
