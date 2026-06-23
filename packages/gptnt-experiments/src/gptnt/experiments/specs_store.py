from __future__ import annotations

from typing import TYPE_CHECKING

from gptnt.experiments.spec import ExperimentSpec

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


def write_specs_to_dir(specs: Iterable[ExperimentSpec], directory: Path) -> list[Path]:
    """Write one JSON file per spec into `directory`, returning the paths written."""
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for spec in specs:
        path = directory.joinpath(spec.attempt_name).with_suffix(".json")
        _ = path.write_text(spec.model_dump_json())
        written.append(path)
    return written


def load_specs_from_dir(directory: Path) -> list[ExperimentSpec]:
    """Load every `*.json` spec under `directory` (recursively), sorted by path for determinism."""
    return [
        ExperimentSpec.model_validate_json(path.read_bytes())
        for path in sorted(directory.rglob("*.json"))
    ]
