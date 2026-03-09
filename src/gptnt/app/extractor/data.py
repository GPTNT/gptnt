import asyncio
from collections import defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import ijson
from streamlit_concurrency import run_in_executor

from gptnt.app.experiment_loader.scanner import ScannedExperiment
from gptnt.players.specification import PlayerRole

# role → {field → [values]}
FileResult = dict[PlayerRole, dict[str, list[Any]]]


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


def _load_and_extract(filepath: Path, paths: list[str]) -> FileResult:
    """One pass through the file, extracting all requested fields simultaneously."""
    local: dict[PlayerRole, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
    with filepath.open("rb") as open_file:
        try:
            for record in ijson.items(open_file, "step_records.item"):
                role = record["role"]
                for path in paths:
                    local[role][path].extend(extract_values(record, path))
        except ijson.IncompleteJSONError as err:
            raise ValueError(
                f"File {filepath} is not a valid JSON file or is incomplete."
            ) from err

    return {role: dict(fields) for role, fields in local.items()}


_load_and_extract_async = run_in_executor(executor="process")(_load_and_extract)


async def _run_one(
    key: ScannedExperiment, filepath: Path, attr_paths: list[str]
) -> tuple[ScannedExperiment, FileResult, Path | None]:
    try:
        extracted = await _load_and_extract_async(filepath, attr_paths)
    except Exception:  # noqa: BLE001
        # We just want to catch any exception so we can look into it more.
        return key, {}, filepath
    else:
        return key, extracted, None


ExtractedGroupedResults = dict[ScannedExperiment, dict[PlayerRole, dict[str, list[Any]]]]


async def extract_across_file_groups(  # noqa: WPS210
    file_groups: dict[ScannedExperiment, list[Path]],
    attr_paths: list[str],
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[ExtractedGroupedResults, list[Path]]:
    """Extract fields from all files in all experiment groups concurrently.

    Args:
        file_groups:       Mapping of experiment → list of result file paths.
        attr_paths:        Dot-notation field paths to extract from each step record.
        progress_callback: Optional callable receiving (completed, total) after each file.

    Returns:
        A tuple of (grouped results, list of broken file paths).
        Grouped results: experiment → role → field → [values].
    """
    # experiment → role → field → [values]
    grouped: ExtractedGroupedResults = {  # noqa: WPS426
        key: defaultdict(lambda: defaultdict(list)) for key in file_groups
    }
    broken_files: list[Path] = []

    tasks = [
        _run_one(key, filepath, attr_paths)
        for key, filepaths in file_groups.items()
        for filepath in filepaths
    ]

    for completed_idx, coro in enumerate(asyncio.as_completed(tasks)):
        key, extracted, broken_filepath = await coro  # noqa: WPS476
        if broken_filepath:
            broken_files.append(broken_filepath)
        else:
            for role, field_values in extracted.items():
                for field, values in field_values.items():  # noqa: WPS110
                    grouped[key][role][field].extend(values)
        if progress_callback is not None:
            progress_callback(completed_idx + 1, len(tasks))

    return (
        {
            experiment: {role: dict(fields) for role, fields in group.items()}  # noqa: WPS441
            for experiment, group in grouped.items()
        },
        broken_files,
    )
