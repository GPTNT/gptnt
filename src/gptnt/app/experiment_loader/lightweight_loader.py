"""Lightweight experiment loading that skips heavy observation and message data."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_core import from_json

from gptnt.players.metrics.records import (
    ExperimentPlayerRecord,
    ExperimentRecord,
    build_experiment_records_from_player_records,
)

if TYPE_CHECKING:
    from gptnt.app.experiment_loader.scanner import ScannedExperiment


def load_player_record_lightweight(file_path: Path) -> ExperimentPlayerRecord:
    """Load a player record from disk, stripping heavy observation and message fields.

    Mutates the raw JSON dict before Pydantic validation to set `observation`,
    `input_messages`, and `new_messages` to empty/null on every step record.
    This avoids deserializing base64-encoded images and large message histories.
    The remaining fields (`output`, `bomb_state`, `usage`, `role`, etc.)
    are sufficient for all :class:`~gptnt.players.metrics.records.StepRecordsMetricsMixin`
    computed metrics.
    """
    raw = from_json(file_path.read_bytes())
    for step in raw.get("step_records", []):
        step["observation"] = None
        step["input_messages"] = []
        step["new_messages"] = []
    return ExperimentPlayerRecord.model_validate(raw)


def _load_all_cached(file_path_keys: tuple[tuple[str, int], ...]) -> list[ExperimentRecord]:
    """Inner cached loader. Cache key is a tuple of `(file_path_str, file_size)` pairs.

    Using file size as part of the key means the cache is automatically invalidated when files are
    added or modified on disk.
    """
    file_paths = [Path(path) for path, _ in file_path_keys]

    with ThreadPoolExecutor(max_workers=32) as executor:
        futures = {executor.submit(load_player_record_lightweight, fp): fp for fp in file_paths}
        player_records = [future.result() for future in as_completed(futures)]

    return build_experiment_records_from_player_records(player_records)


def load_all_experiments_lightweight(
    experiments: list[ScannedExperiment],
) -> list[ExperimentRecord]:
    """Load all scanned experiments in a lightweight way (no observations or messages).

    Collects all file paths from the provided :class:`~gptnt.app.experiment_loader.scanner.ScannedExperiment`
    instances, loads them in parallel using a thread pool, then collates player
    records into :class:`~gptnt.players.metrics.records.ExperimentRecord` instances
    grouped by session UUID.

    Results are cached by `(file_path, file_size)` pairs, so the cache is
    automatically invalidated when files change on disk.
    """
    all_file_paths: list[Path] = []
    for exp in experiments:
        all_file_paths.extend(exp.file_paths)

    # Build cache key from (path, file_size) so the cache busts when files change
    file_path_keys = tuple((str(fp), fp.stat().st_size) for fp in all_file_paths)

    return _load_all_cached(file_path_keys)
