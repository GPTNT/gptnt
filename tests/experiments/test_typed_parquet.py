"""Round-trip tests for the typed pydantic-model ⇄ parquet layer."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic_ai import RunUsage

from gptnt.experiments.db.typed_parquet import read_typed_parquet, write_typed_parquet
from gptnt.experiments.models import ExperimentStep, ExperimentSummary
from gptnt.players.actions import DoNothingAction

from tests._factories.experiments import make_experiment_summary

if TYPE_CHECKING:
    from pathlib import Path


def test_round_trips_summaries_through_json_columns(tmp_path: Path) -> None:
    """The AsJSON fields (descriptor, capabilities) parse back into models after a write/read."""
    summaries = [
        make_experiment_summary(defuser_name="model-a", seed=1),
        make_experiment_summary(defuser_name="model-b", is_solved=False, seed=2),
    ]
    path = tmp_path / "summaries.parquet"
    write_typed_parquet(summaries, file_path=path)

    assert read_typed_parquet(ExperimentSummary, path) == summaries


def test_round_trips_blob_and_varchar_step_fields(tmp_path: Path) -> None:
    """The AsBlob (usage) and AsVarchar (output) columns restore to the original step."""
    step = ExperimentStep(
        step=0,
        timestamp=1.0,
        role="defuser",
        session_id=uuid4(),
        player_uuid=uuid4(),
        player_name="model-a",
        output=DoNothingAction(),
        raw_output="DoNothing",
        input_messages=[],
        new_messages=[],
        bomb_state=None,
        observation=None,
        usage=RunUsage(requests=1, input_tokens=10, output_tokens=2),
        num_prompt_truncations=0,
    )
    path = tmp_path / "steps.parquet"
    write_typed_parquet([step], file_path=path)

    assert read_typed_parquet(ExperimentStep, path) == [step]
