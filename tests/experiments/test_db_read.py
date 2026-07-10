"""Tests for the DuckDB read helpers that back submission bundling."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import duckdb
import pyarrow as pa
from pydantic_ai import RunUsage

from gptnt.experiments.db.ingest import ensure_schema
from gptnt.experiments.db.read import load_final_states_and_usage
from gptnt.experiments.db.schema import EXPORT_CONTEXT_MARKER
from gptnt.experiments.models import ExperimentStep
from gptnt.ktane.state.bomb import BombState
from gptnt.players.actions import DoNothingAction

if TYPE_CHECKING:
    from pathlib import Path
    from uuid import UUID

    from gptnt.players.specification import PlayerRole


def _solved_bomb() -> BombState:
    return BombState.model_validate(
        {
            "seed": 1,
            "maxStrikes": 3,
            "strikes": None,
            "isDetonated": False,
            "isSolved": True,
            "isLightOn": True,
            "bombSide": "front",
            "timerModule": {
                "name": "Timer",
                "onFront": True,
                "index": 0,
                "secondsRemaining": 42.0,
            },
            "widgets": [],
            "modules": [
                {
                    "wires": [{"position": 0, "isCut": True, "color": "red"}],
                    "isSolved": True,
                    "inFocus": False,
                    "onFront": True,
                    "index": 1,
                    "name": "Wires",
                }
            ],
        }
    )


def _step(
    *, session_id: UUID, role: PlayerRole, step: int, usage: RunUsage, bomb_state: BombState | None
) -> ExperimentStep:
    return ExperimentStep(
        step=step,
        timestamp=float(step),
        role=role,
        session_id=session_id,
        player_uuid=uuid4(),
        player_name=f"model-{role}",
        output=DoNothingAction(),
        raw_output="DoNothing",
        input_messages=[],
        new_messages=[],
        bomb_state=bomb_state,
        observation=None,
        usage=usage,
        num_prompt_truncations=0,
    )


def _write_steps(db_path: Path, steps: list[ExperimentStep]) -> None:
    ensure_schema(db_path)
    rows = [step.model_dump(context={"mode": EXPORT_CONTEXT_MARKER}) for step in steps]
    with duckdb.connect(str(db_path)) as con:
        _ = con.register("new_steps", pa.Table.from_pylist(rows))
        _ = con.execute("INSERT INTO experiment_step BY NAME SELECT * FROM new_steps")
        _ = con.unregister("new_steps")


def test_load_final_states_and_usage_takes_last_bomb_state_and_sums_per_role(
    tmp_path: Path,
) -> None:
    """The final state is the last non-null bomb state; usage sums separately per player role."""
    session_id = uuid4()
    db_path = tmp_path / "experiments.duckdb"
    _write_steps(
        db_path,
        [
            _step(
                session_id=session_id,
                role="defuser",
                step=0,
                usage=RunUsage(requests=1, input_tokens=10, output_tokens=2),
                bomb_state=None,
            ),
            _step(
                session_id=session_id,
                role="defuser",
                step=1,
                usage=RunUsage(requests=1, input_tokens=20, output_tokens=3),
                bomb_state=_solved_bomb(),
            ),
            _step(
                session_id=session_id,
                role="expert",
                step=0,
                usage=RunUsage(requests=1, input_tokens=5, output_tokens=1),
                bomb_state=None,
            ),
        ],
    )

    final_state, usage_by_role = load_final_states_and_usage(db_path, [session_id])[session_id]

    assert final_state.is_solved
    assert (usage_by_role["defuser"].input_tokens, usage_by_role["defuser"].output_tokens) == (
        30,
        5,
    )
    assert (usage_by_role["expert"].input_tokens, usage_by_role["expert"].output_tokens) == (5, 1)


def test_load_final_states_and_usage_is_empty_for_no_session_ids(tmp_path: Path) -> None:
    """No session ids means no query and an empty result, not a crash."""
    db_path = tmp_path / "experiments.duckdb"
    ensure_schema(db_path)

    assert load_final_states_and_usage(db_path, []) == {}
