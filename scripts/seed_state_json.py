"""JSON cleanup for bomb states collected by the seed-ranking script."""

from pathlib import Path
from typing import Any

import orjson


def _remove_keys_recursively(data: Any, keys_to_remove: tuple[str, ...]) -> None:
    """Remove selected keys from nested dictionaries and lists in place."""
    if isinstance(data, dict):
        for key in keys_to_remove:
            data.pop(key, None)
        for value in data.values():
            _remove_keys_recursively(value, keys_to_remove)
    elif isinstance(data, list):
        for item in data:
            _remove_keys_recursively(item, keys_to_remove)


def dump_unneeded_info(file_path: Path) -> None:
    """Remove volatile bomb-state fields and rewrite the JSON with two-space indentation."""
    data = orjson.loads(file_path.read_bytes())
    del data["timerModule"]["secondsRemaining"]

    keys_to_remove = (
        "isHeld",
        "isSolved",
        "inFocus",
        "stage",
        "numRows",
        "numColumns",
        "solveProgress",
        "panel",
        "stripColor",
        "name",
        "isCut",
    )
    if "modules" in data:
        for module in data["modules"]:
            _remove_keys_recursively(module, keys_to_remove)

            if all(key in module for key in ("topLeft", "topRight", "bottomLeft", "bottomRight")):
                for position in ("topLeft", "topRight", "bottomLeft", "bottomRight"):
                    if "color" in module[position]:
                        del module[position]["color"]

    _ = file_path.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2))
