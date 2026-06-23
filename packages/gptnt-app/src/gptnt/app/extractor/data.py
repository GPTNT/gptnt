from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Any

from gptnt.experiments.db.connection import DuckDBConnection
from gptnt.experiments.duckdb import EXPORT_CONTEXT_MARKER
from gptnt.experiments.models import ExperimentMetadata, ExperimentStepRecord

# Columns excluded from the SELECT to avoid pulling large compressed blobs.
# The model validator (optionally_skip_heavy_objects) already sets these to
# None / [] when skip_heavy_field_loading=True, so they don't need to be fetched.
_HEAVY_COLUMNS: frozenset[str] = frozenset(("observation", "input_messages", "new_messages"))

_QUERY_BATCH_SIZE = 500


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


# One dict per step: experiment metadata + role + extracted field values.
StepRow = dict[str, Any]


def extract_from_step_records_db(  # noqa: WPS210, WPS231
    *,
    connection: DuckDBConnection,
    experiments: list[ExperimentMetadata],
    fields: list[str],
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[StepRow]:
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
        A flat list of row dicts, one per step, ready to be passed to `results_to_dataframe`.
    """
    if not experiments:
        return []

    session_map: dict[str, ExperimentMetadata] = {str(exp.session_id): exp for exp in experiments}

    col_select = ", ".join(
        col
        for col in ExperimentStepRecord.model_fields
        if col not in _HEAVY_COLUMNS  # noqa: WPS110
    )
    table = ExperimentStepRecord.table_name()

    # Pre-group raw rows by session_id before deserialisation, querying in batches
    # to avoid materialising a huge result set and to stay within parameter limits.
    rows_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    session_ids = list(session_map.keys())
    col_names: list[str] = []

    for batch_start in range(0, len(session_ids), _QUERY_BATCH_SIZE):
        batch = session_ids[batch_start : batch_start + _QUERY_BATCH_SIZE]
        placeholders = ", ".join("?" * len(batch))
        query = connection.execute(
            f"SELECT {col_select} FROM {table} WHERE session_id IN ({placeholders})",  # noqa: S608
            batch,
        )
        if not col_names:
            col_names = [desc[0] for desc in query.description]
        for row in query.fetchall():
            row_dict = dict(zip(col_names, row, strict=False))
            rows_by_session[str(row_dict["session_id"])].append(row_dict)

    step_rows: list[StepRow] = []
    total = len(experiments)
    for idx, exp in enumerate(experiments):
        exp_dict = exp.model_dump(mode="json", by_alias=True)
        for row_dict in rows_by_session.get(str(exp.session_id), []):
            step = ExperimentStepRecord.model_validate(
                row_dict, context={"skip_heavy_field_loading": True, "mode": EXPORT_CONTEXT_MARKER}
            )
            step_rows.append(
                {
                    **exp_dict,
                    "role": step.role,
                    **{field: extract_values(step, field) for field in fields},
                }
            )

        if progress_callback is not None:
            progress_callback(idx + 1, total)

    return step_rows
