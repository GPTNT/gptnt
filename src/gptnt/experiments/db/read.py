"""Read experiment summaries and per-experiment final state/usage from the DuckDB database."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

import duckdb
from pydantic import TypeAdapter
from pydantic_ai import RunUsage

from gptnt.experiments.db.schema import AsBlob
from gptnt.experiments.models import ExperimentStep, ExperimentSummary
from gptnt.ktane.state.bomb import BombState

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path
    from uuid import UUID


def load_experiment_summaries(
    db_path: Path,
    *,
    suite_name: str | None = None,
    suite_revision: int | None = None,
    model_names: Iterable[str] | None = None,
) -> list[ExperimentSummary]:
    """Load experiment summary rows, optionally filtered by suite, revision, and defuser model.

    This is just a wrapper around a DuckDB SQL query.
    """
    clauses: list[str] = []
    params: list[object] = []
    if suite_name is not None:
        clauses.append("suite_name = ?")
        params.append(suite_name)
    if suite_revision is not None:
        clauses.append("suite_revision = ?")
        params.append(suite_revision)
    names = list(model_names or [])
    if names:
        clauses.append(f"defuser_name IN ({', '.join('?' * len(names))})")
        params.extend(names)

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

    with duckdb.connect(str(db_path), read_only=True) as con:
        output = con.execute(
            f"SELECT * FROM {ExperimentSummary.table_name()}{where}",  # noqa: S608
            params,
        )
        columns = [desc[0] for desc in output.description]
        return [
            ExperimentSummary.model_validate(dict(zip(columns, row, strict=False)))
            for row in output.fetchall()
        ]


type _BombStateCells = list[str | None]
type _UsageCells = list[bytes]

_USAGE_LIST_ADAPTER = TypeAdapter(list[RunUsage])


def _group_cells_by_session(
    rows: list[tuple[UUID, str | None, bytes]],
) -> tuple[dict[UUID, _BombStateCells], dict[UUID, _UsageCells]]:
    """Split step-ordered `(session_id, bomb_state, usage)` rows into per-session columns."""
    bomb_states: dict[UUID, _BombStateCells] = defaultdict(list)
    usage_cells: dict[UUID, _UsageCells] = defaultdict(list)
    for session_id, bomb_state, usage in rows:
        bomb_states[session_id].append(bomb_state)
        usage_cells[session_id].append(usage)
    return bomb_states, usage_cells


def _get_final_bomb_state(bomb_states: _BombStateCells) -> BombState:
    """The last non-null bomb state of one experiment's steps, which _should_ exist."""
    final = next(
        (BombState.model_validate_json(bs) for bs in reversed(bomb_states) if bs is not None), None
    )
    if final is None:
        raise ValueError("No final bomb state found in the steps of experiment.")
    return final


def _sum_usage(usage_cells: _UsageCells) -> RunUsage:
    """Sum the usage from one experiment's blobbed usage cells."""
    decoded = _USAGE_LIST_ADAPTER.validate_python([AsBlob.from_blob(cell) for cell in usage_cells])
    return sum(decoded, RunUsage())


def load_final_states_and_usage(
    db_path: Path, session_ids: Iterable[UUID]
) -> dict[UUID, tuple[BombState, RunUsage]]:
    """Per experiment: the final bomb state and the summed usage, from the step table.

    Only the `bomb_state` (JSON) and `usage` (compressed BLOB) columns are read — never the large
    image/message blobs. The final bomb state is the last non-null one by step (it lives only on
    the defuser's steps); an experiment that never reached one is an error, not a skip.
    """
    ids = [str(session_id) for session_id in session_ids]
    if not ids:
        return {}

    placeholders = ", ".join("?" * len(ids))
    with duckdb.connect(str(db_path), read_only=True) as con:
        rows = con.execute(
            f"SELECT session_id, bomb_state, usage FROM {ExperimentStep.table_name()} "  # noqa: S608
            f"WHERE session_id IN ({placeholders}) ORDER BY session_id, step",
            ids,
        ).fetchall()

    bomb_states, usage_cells = _group_cells_by_session(rows)
    return {
        session_id: (
            _get_final_bomb_state(bomb_states[session_id]),
            _sum_usage(usage_cells[session_id]),
        )
        for session_id in bomb_states
    }
