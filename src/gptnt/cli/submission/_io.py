"""Filesystem and config helpers shared by `submission new` and `submission validate`."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import hydra
import pyarrow as pa
import yaml
from pyarrow import parquet as pq

from gptnt.cli.submission._schema import SubmissionExperiment
from gptnt.common.hydra import load_config
from gptnt.experiments.generation.pipeline import CONFIG_NAME

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.experiments.suite import Suite

_RECORD_GLOB = "experiment-*.parquet"


def load_suite(suite_name: str) -> Suite:
    """Compose and instantiate one suite exactly as generation and `test_frozen_suites` do."""
    return hydra.utils.instantiate(
        load_config(config_name=CONFIG_NAME, overrides=[f"suites={suite_name}"]).suite
    )


def find_player_records(outputs_dir: Path) -> list[Path]:
    """Every recorded player parquet under an outputs directory."""
    return sorted(outputs_dir.rglob(_RECORD_GLOB))


def read_yaml(path: Path) -> dict[str, Any]:
    """Parse a YAML file into a plain dict."""
    return yaml.safe_load(path.read_text())


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write a dict to YAML, preserving key order and block style."""
    _ = path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))


def write_experiments(path: Path, experiments: list[SubmissionExperiment]) -> None:
    """Write the per-experiment rows to `experiments.parquet`."""
    table = pa.Table.from_pylist([experiment.to_row() for experiment in experiments])
    _ = pq.write_table(table, path)


def read_experiments(path: Path) -> list[SubmissionExperiment]:
    """Read `experiments.parquet` back into typed rows."""
    return [SubmissionExperiment.from_row(row) for row in pq.read_table(path).to_pylist()]


def write_predictions(path: Path, predictions: list[dict[str, Any]]) -> None:
    """Write statics predictions to `predictions.parquet`, one JSON-string row per prediction.

    The predictions are already image-free (index, usage, model, output, thoughts, raw output,
    error), so each is stored whole as a JSON string keyed by its instance index.
    """
    rows = [
        {"index": prediction["index"], "prediction": json.dumps(prediction)}
        for prediction in predictions
    ]
    _ = pq.write_table(pa.Table.from_pylist(rows), path)


def read_predictions(path: Path) -> list[dict[str, Any]]:
    """Read `predictions.parquet` back into prediction dicts."""
    return [json.loads(row["prediction"]) for row in pq.read_table(path).to_pylist()]
