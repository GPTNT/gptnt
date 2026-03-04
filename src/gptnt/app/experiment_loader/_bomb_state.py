from __future__ import annotations

import mmap
from contextlib import suppress
from typing import TYPE_CHECKING

import structlog

from gptnt.ktane.state.bomb import BombState

logger = structlog.get_logger()

if TYPE_CHECKING:
    from pathlib import Path


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
