import asyncio
from pathlib import Path
from typing import cast

import streamlit as st

from gptnt.app.components.filters import Filters, apply_filters
from gptnt.app.experiment_loader.scanner import ScannedExperiment
from gptnt.app.extractor.components import render_field_input
from gptnt.app.extractor.data import ExtractedGroupedResults, extract_across_file_groups
from gptnt.app.extractor.dataframe import results_to_dataframe


def extract_data_from_files(
    *, file_groups: dict[ScannedExperiment, list[Path]], fields: list[str], num_total_files: int
) -> tuple[ExtractedGroupedResults, list[Path]]:
    """Extract specified fields from files grouped by experiment.

    Args:
        file_groups: Mapping of experiment → list of file paths to extract from.
        fields: List of field names to extract from each file.
        num_total_files: Total number of files to be processed.
    """
    # 2b. Extract across all files concurrently
    progress_bar = st.progress(0, text="Loading files…")

    def _update_progress(completed: int, total: int) -> None:  # noqa: WPS430
        fraction = completed / total if total else 1.0
        _ = progress_bar.progress(fraction, text=f"Loaded {completed} / {total} files…")

    extracted_data, broken_files = asyncio.run(
        extract_across_file_groups(file_groups, fields, progress_callback=_update_progress)
    )

    if broken_files:
        _ = st.warning(f"{len(broken_files)} files skipped due to errors.")
        for path in broken_files:
            _ = st.caption(f" - {path}")

    _ = progress_bar.progress(1.0, text=f"Done — {num_total_files} files loaded.")

    return extracted_data, broken_files


def render_extractor_view(scanned_experiments: list[ScannedExperiment], filters: Filters) -> None:
    """Orchestrate the full field-extraction UI.

    Pipeline:
        1. Render field input widget → obtain fields + button state
        2. On button press: apply filters, extract fields across all matching files,
           build the result DataFrame, display progress throughout
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
        filtered_experiments = apply_filters(scanned_experiments, filters)
        file_groups = {exp: exp.file_paths for exp in filtered_experiments}

        total_files = sum(len(fps) for fps in file_groups.values())
        st.write(
            f"Extracting {len(fields)} field(s) across "
            f"{len(file_groups)} experiments ({total_files} files)..."
        )

        extracted_data, broken_files = extract_data_from_files(
            file_groups=file_groups, fields=fields, num_total_files=total_files
        )

        # 2c. Build DataFrame
        st.write("Building dataframe...")
        df = results_to_dataframe(extracted_data, fields)

        status.update(
            label=f":material/grading: Extracted from {len(file_groups)} experiments, skipped {len(broken_files)}.",
            state="complete",
            expanded=bool(broken_files),
        )

    # 3. Download + preview
    with st.container(horizontal=True, vertical_alignment="center"):
        _ = st.caption("Showing up to 50 rows. Use the download button to get everything.")
        json_name = "__".join(fields)
        _ = st.download_button(
            label="Download JSON",
            data=cast("str", df.to_json(orient="records")),
            file_name=f"{json_name}.json",
            mime="application/json",
            type="primary",
        )
    _ = st.markdown("**Preview**")
    _ = st.dataframe(df.head(50))
