from collections import defaultdict
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd
import st_tailwind as tw
import streamlit as st
from pydantic_core import from_json

from gptnt.app.app_state import get_state
from gptnt.app.components.filters import apply_filters, render_filters
from gptnt.app.experiment_loader.components import render_db_status
from gptnt.app.loader_page import load_options_for_filters
from gptnt.players.metrics.records import ExperimentStepRecord
from gptnt.players.specification import PlayerRole

_ = tw.initialize_tailwind()


def extract_values(obj: Any, path: str) -> list[Any]:  # noqa: WPS110
    """Traverse an object following a dot-notation path, collecting all leaf values.

    Path syntax:
        - `field`    → access attribute directly (scalar)
        - `field[]`  → field is a list; iterate and fan out

    Example paths:
        "bomb_state.modules[].module_name"
        "error_type[]"
        "bomb_state.modules[].wires[].color"

    Args:
        obj:  The root object to traverse (e.g. an ExperimentStepRecord).
        path: Dot-separated path string.

    Returns:
        A flat list of all matching leaf values.
    """
    levels = path.split(".")
    return _recurse(obj, levels)


def _recurse(current: Any, levels: list[str]) -> list[Any]:  # noqa: WPS212
    if not levels:
        return [current]
    if current is None:
        return []

    level = levels[0]
    remaining = levels[1:]
    is_list = level.endswith("[]")
    field_name = level.removesuffix("[]")

    field_value = (
        current.get(field_name)
        if isinstance(current, dict)
        else getattr(current, field_name, None)
    )

    if field_value is None:
        return []

    if is_list:
        if not isinstance(field_value, Sequence):
            return []
        collected = []
        for element in field_value:
            collected.extend(_recurse(element, remaining))
        return collected

    return _recurse(field_value, remaining)


def load_records(filepath: Path) -> list[ExperimentStepRecord]:
    """Load ExperimentStepRecord objects from a single file."""
    json_data = from_json(filepath.read_bytes())
    raw_step_records = json_data["step_records"]
    parsed_step_records = [
        ExperimentStepRecord.model_validate(record, context={"skip_heavy_field_loading": True})
        for record in raw_step_records
    ]
    return parsed_step_records


def _load_and_extract(filepath: Path, path: str) -> dict[PlayerRole, list[Any]]:
    """Load records from one file and extract values at `path`, grouped by role.

    Runs entirely in a worker thread — safe to call in parallel across files.
    """
    local: dict[PlayerRole, list[Any]] = defaultdict(list)
    for record in load_records(filepath):
        local[record.role].extend(extract_values(record, path))
    return dict(local)


def _extract_across_file_groups(
    file_groups: dict[str, list[Path]], path: str
) -> dict[str, dict[PlayerRole, list[Any]]]:
    """Load all files across all groups in parallel, return one grouped result per key."""
    grouped: dict[str, dict[PlayerRole, list[Any]]] = {
        key: defaultdict(list) for key in file_groups
    }

    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(_load_and_extract, filepath, path): key
            for key, filepaths in file_groups.items()
            for filepath in filepaths
        }
        for future in as_completed(futures):
            key = futures[future]
            for role, extracted_values in future.result().items():
                grouped[key][role].extend(extracted_values)

    return {key: dict(group) for key, group in grouped.items()}


def _results_to_dataframe(
    extracted_data: dict[str, dict[PlayerRole, list[Any]]], field: str
) -> pd.DataFrame:
    rows = [
        {"experiment": experiment_name, "role": role, field: extracted_values}
        for experiment_name, grouped in extracted_data.items()
        for role, extracted_values in grouped.items()
    ]
    return pd.DataFrame(rows)


def extractor_page() -> None:  # noqa: WPS210
    """Descriptive statistics grabbing for the data."""
    state = get_state()

    _ = st.header("Get statistics")
    _ = st.caption(
        "The whole purpose of this is to pick a field and get some data as fast as possible. You should also filter because otherwise you might be waiting a while."
    )

    with st.sidebar:
        render_db_status(state.loader)
        _ = st.divider()
    if not state.loader.db_exists:
        st.stop()

    experiments_to_load = state.loader.scanned_experiments
    options = load_options_for_filters()
    filters = render_filters(options, expanded=False)

    with st.container(horizontal=True, vertical_alignment="bottom"):
        field_to_aggregate = st.text_input(
            "Field to aggregate (from ExperimentStepRecord)",
            placeholder="e.g. bomb_state.modules[].module_name",
        )
        button = st.button("Extract", disabled=not field_to_aggregate, type="primary")

    if button:
        with st.status("Running...", expanded=True) as status:
            st.write("Applying filters...")
            experiments_to_load = apply_filters(experiments_to_load, filters)
            file_groups = {exp.experiment_name: exp.file_paths for exp in experiments_to_load}

            st.write(f"Extracting `{field_to_aggregate}` across {len(file_groups)} experiments...")
            extracted_data = _extract_across_file_groups(file_groups, field_to_aggregate)

            st.write("Building dataframe...")
            df = _results_to_dataframe(extracted_data, field_to_aggregate)

            status.update(
                label=f":material/grading: Extracted data from {len(file_groups)} experiments.",
                state="complete",
                expanded=False,
            )

        with st.container(horizontal=True, vertical_alignment="center"):
            _ = st.caption("Showing up to 50 rows. Use the download button to get everything.")
            _ = st.download_button(
                label="Download CSV",
                data=df.to_csv(index=False),
                file_name=f"{field_to_aggregate}.csv",
                mime="text/csv",
                type="primary",
            )
        _ = st.markdown("**Preview**")
        _ = st.dataframe(df.head(50))
