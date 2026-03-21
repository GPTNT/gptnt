from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Any

import pandas as pd

from gptnt.records.db.connection import DuckDBConnection
from gptnt.records.models import ExperimentMetadata, ExperimentStepRecord
from gptnt.specification import PlayerRole


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


ExtractedGroupedResults = dict[ExperimentMetadata, dict[PlayerRole, dict[str, list[Any]]]]


def extract_from_step_records_db(  # noqa: WPS210
    *,
    connection: DuckDBConnection,
    experiments: list[ExperimentMetadata],
    fields: list[str],
    progress_callback: Callable[[int, int], None] | None = None,
) -> ExtractedGroupedResults:
    """Extract fields from ExperimentStepRecord rows in DuckDB.

    Fetches all relevant step records in a single query, then extracts the requested dot-notation
    field paths from each deserialized record.

    I've also kept everything in this one func just to keep it together and easier to read.

    Args:
        connection:        Active DuckDB connection.
        experiments:       Experiments whose step records to query (filtered already).
        fields:            Dot-notation field paths to extract from each step record.
        progress_callback: Optional callable receiving (completed, total)
                           after each experiment's rows are processed.

    Returns:
        experiment → role → field → [values], same shape as the old file-based output.
    """
    if not experiments:
        return {}

    session_map: dict[str, ExperimentMetadata] = {str(exp.session_id): exp for exp in experiments}

    # Single query for all sessions
    placeholders = ", ".join("?" * len(experiments))
    query = connection.execute(
        f"SELECT * FROM {ExperimentStepRecord.table_name()} WHERE session_id IN ({placeholders})",  # noqa: S608
        list(session_map.keys()),
    )
    col_names = [desc[0] for desc in query.description]

    # Pre-group raw rows by session_id before deserialisation
    rows_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in query.fetchall():
        row_dict = dict(zip(col_names, row, strict=False))
        rows_by_session[str(row_dict["session_id"])].append(row_dict)

    grouped: ExtractedGroupedResults = {  # noqa: WPS426
        exp: defaultdict(lambda: defaultdict(list)) for exp in experiments
    }

    total = len(experiments)
    for idx, exp in enumerate(experiments):
        for row_dict in rows_by_session.get(str(exp.session_id), []):
            # Skip observation/messages blobs
            step = ExperimentStepRecord.model_validate(
                row_dict, context={"skip_heavy_field_loading": True}
            )
            role = step.role
            for field_path in fields:
                field_values = extract_values(step, field_path)
                grouped[exp][role][field_path].extend(field_values)

        if progress_callback is not None:
            progress_callback(idx + 1, total)

    return {
        exp_metadata: {role: dict(field_vals) for role, field_vals in group.items()}
        for exp_metadata, group in grouped.items()
    }


def results_to_dataframe(
    extracted_data: dict[ExperimentMetadata, dict[PlayerRole, dict[str, list[Any]]]],
) -> pd.DataFrame:
    """Convert extracted field data into a flat DataFrame.

    Each row represents one (experiment, role) combination, with extracted
    field values as additional columns alongside experiment metadata.

    Args:
        extracted_data: experiment → role → field → [values], as returned by
                        ``extract_across_file_groups``.
        fields:         Ordered list of extracted field names, used as column headers.
    """
    rows = [
        {**experiment.model_dump(mode="json", by_alias=True), "role": role, **field_values}
        for experiment, grouped in extracted_data.items()
        for role, field_values in grouped.items()
    ]
    return pd.DataFrame(rows)
