import mmap
from collections import defaultdict
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path
from typing import Any

import duckdb
import ijson
import structlog
from rich.progress import Progress

from gptnt.common.duckdb import EXPORT_CONTEXT_MARKER
from gptnt.common.logger import ProgressSentinel, with_default_progress
from gptnt.experiments.experiment_descriptor import ExperimentDescriptor
from gptnt.ktane.state.bomb import BombState
from gptnt.records.models import ExperimentMetadata, ExperimentStepRecord, is_valid_experiment

logger = structlog.get_logger()

type DumpedExperimentMetadata = dict[str, Any]
type BlobbedStepRecord = dict[str, Any]


BOMB_STATE_MARKER = b'"bomb_state":'
MAX_BOMB_STATE_BYTES = 256 * 1024  # Generous upper bound (256 KB)

WHITESPACE = frozenset(b" \t\n\r")
BACKSLASH = 0x5C
QUOTE = 0x22
OPEN_CURLYBRACE = 0x7B
CLOSE_CURLYBRACE = 0x7D


def _find_json_object_end(data: bytes, start: int = 0) -> int | None:  # noqa: WPS231
    """Return the offset one past the closing `}` of the outermost JSON object.

    Handles nested objects and ignores brace characters inside strings (including escaped quotes).
    Returns `None` if the object is not fully contained in the data.
    """
    depth = 0
    in_string = False
    escaped = False

    for position, byte_data in enumerate(data[start:], start):
        if escaped:  # noqa: WPS223
            escaped = False
        elif in_string:
            if byte_data == BACKSLASH:
                escaped = True
            elif byte_data == QUOTE:
                in_string = False
        elif byte_data == QUOTE:
            in_string = True
        elif byte_data == OPEN_CURLYBRACE:
            depth += 1
        elif byte_data == CLOSE_CURLYBRACE:
            depth -= 1
            if depth == 0:
                return position + 1

    return None


def grab_last_bomb_state_from_experiment_file(file_path: Path) -> BombState | None:  # noqa: WPS212
    """Return the last non-null BombState from file_path using mmap tail-scan.

    Maps the file into virtual memory and uses `mmap.rfind` to locate the last `"bomb_state":`
    token. Only the bytes of that single JSON object are brought into physical memory, making this
    O(object size) rather than O(file size).

    Why all the exception suppressing?

    We want to just get through this and return None if something is not available, because the
    bomb state might not be available and we don't know until we try. The files are huge and I
    (think) I made a bad decision when I was doing this data dumping. So we are here now.

    - `file_path.open()` fails = OSError
    - `mmap.mmap()` fail - underlying I/O error = OSError
    - `mm.rfind()` fails = shouldn't raise, but if the file is truncated or corrupted it could raise ValueError
    - JSON parsing fails = ValueError, IndexError, KeyError depending on the nature
    - `mm[pos]` out of range = IndexError
    """
    with (
        suppress(ValueError, KeyError, IndexError, OSError),
        file_path.open("rb") as fh,
        mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm,
    ):
        pos = mm.rfind(BOMB_STATE_MARKER)
        if pos == -1:
            return None

        pos += len(BOMB_STATE_MARKER)

        # Skip whitespace between ':' and the value
        while pos < len(mm) and mm[pos] in WHITESPACE:
            pos += 1

        # null → bomb not yet set
        if mm[pos : pos + 1] == b"n":
            return None
        if mm[pos : pos + 1] != b"{":
            return None

        chunk = bytes(mm[pos : pos + MAX_BOMB_STATE_BYTES])
        end = _find_json_object_end(chunk)
        if end is None:
            logger.warning(
                "bomb_state object truncated or exceeds size limit", file=str(file_path)
            )
            return None

        return BombState.model_validate_json(chunk[:end])

    logger.warning("Failed to extract bomb state", file=str(file_path))
    return None


def extract_metadata_from_paths(paths: list[Path]) -> DumpedExperimentMetadata:
    """Extract the metadata from the paths efficiently, and return it as a dictionary.

    We parse it into an ExperimentMetadata and then dump it back to a dict to ensure that we only
    return JSON-serializable data, and also to decouple the DB layer from the internal data model.
    """
    with paths[0].open("rb") as open_file:
        experiment_descriptor = ExperimentDescriptor.model_validate(
            next(ijson.items(open_file, "experiment_descriptor"))
        )

    is_hard_crash = False
    for path in paths:
        with path.open("rb") as open_file:
            is_hard_crash: bool = next(ijson.items(open_file, "is_hard_crash"))
            if is_hard_crash:
                break

    final_bomb_state = None
    for path in paths:
        bomb_state = grab_last_bomb_state_from_experiment_file(path)
        if bomb_state is not None:
            final_bomb_state = bomb_state
            break

    assert final_bomb_state is not None, "No bomb state found in any of the provided files"

    return ExperimentMetadata.from_descriptor_and_bomb_state(
        descriptor=experiment_descriptor,
        final_bomb_state=final_bomb_state,
        file_paths=paths,
        is_valid=is_valid_experiment(
            is_hard_crash=is_hard_crash, final_bomb_state=final_bomb_state
        ),
    ).model_dump(mode="json")


def iter_blobbed_step_records(paths: list[Path]) -> Iterator[BlobbedStepRecord]:
    """Stream step records one at a time as blobbed dictionaries.

    Yields one record at a time without accumulating a list, keeping memory bounded to a single
    step record at a time regardless of how many steps are in the files.
    """
    for path in paths:
        with path.open("rb") as open_file:
            for step in ijson.items(open_file, "step_records.item"):
                yield ExperimentStepRecord.model_validate(step).model_dump(
                    context={"mode": EXPORT_CONTEXT_MARKER}
                )


def group_by_unique_experiment(
    file_paths: list[Path], *, uuid_length: int = 36
) -> dict[str, list[Path]]:
    """Group experiment files by base config, stripping the trailing player UUID."""
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in file_paths:
        base = path.stem[: -(uuid_length + 1)]
        grouped[base].append(path)
    return grouped


@with_default_progress()
def filter_existing_experiments(
    file_paths: list[Path],
    *,
    connection: duckdb.DuckDBPyConnection,
    progress: Progress = ProgressSentinel,
) -> list[Path]:
    """Return only paths that have not yet been ingested.

    Compares against ``file_names`` in ``experiment_metadata`` so that
    ingestion is idempotent and safe to re-run without creating duplicates.
    """
    assert progress is not None
    task = progress.add_task("Checking for existing experiments in DB", total=None)

    if not file_paths:
        progress.update(task, completed=1, total=1)
        return []

    existing_names: set[str] = {
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT unnest(file_names) FROM experiment_metadata"
        ).fetchall()
    }

    progress.update(task, completed=1, total=1)
    return [p for p in file_paths if p.name not in existing_names]  # noqa: WPS111
