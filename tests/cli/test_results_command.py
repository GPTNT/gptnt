"""End-to-end test of the `gptnt results` command against a temporary DuckDB."""

from __future__ import annotations

from typing import TYPE_CHECKING

import duckdb
import pyarrow as pa
import pytest

from gptnt.cli.__main__ import build_app
from gptnt.cli.experiments.results import show_results
from gptnt.experiments.db.ingest import ensure_schema
from gptnt.experiments.db.schema import EXPORT_CONTEXT_MARKER

from tests._cli_runner import invoke_cli
from tests._factories.experiments import make_experiment_summary

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.experiments.models import ExperimentSummary


def _write_db(db_path: Path, summaries: list[ExperimentSummary]) -> None:
    """Create the schema and insert summaries, the same dump path ingestion uses."""
    ensure_schema(db_path)
    rows = [summary.model_dump(context={"mode": EXPORT_CONTEXT_MARKER}) for summary in summaries]
    with duckdb.connect(str(db_path)) as con:
        _ = con.register("new_summaries", pa.Table.from_pylist(rows))
        _ = con.execute("INSERT INTO experiment_summary BY NAME SELECT * FROM new_summaries")
        _ = con.unregister("new_summaries")


def test_results_lists_outcomes_and_dims_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valid runs become rows; invalid runs only name their attempt in the caption."""
    monkeypatch.setenv("COLUMNS", "200")  # keep rich from truncating cells in the captured pipe
    db_path = tmp_path / "experiments.duckdb"
    _write_db(
        db_path,
        [
            make_experiment_summary(
                defuser_name="model-a", expert_name="model-a", is_solved=True, seed=110
            ),
            make_experiment_summary(
                defuser_name="model-b",
                expert_name="model-b",
                is_solved=False,
                is_timed_out=True,
                num_modules_solved=1,
                seed=222,
            ),
            make_experiment_summary(
                defuser_name="model-c",
                is_solved=False,
                is_strike_out=True,
                num_modules_solved=0,
                seed=333,
            ),
            make_experiment_summary(
                defuser_name="model-x", is_hard_crash=True, is_solved=False, seed=999
            ),
        ],
    )

    result = invoke_cli(build_app(), ["results", "--db-path", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "solved" in result.output
    assert "timeout" in result.output
    assert "strikeout" in result.output
    # The hard-crashed run is named only in the invalid caption, never as a row.
    assert "invalid (1)" in result.output
    assert result.output.count("model-x") == 1
    # Rows are ordered by mission key (ascending seed here), so model-a precedes model-c.
    assert result.output.index("model-a") < result.output.index("model-c")


def test_missing_database_raises(tmp_path: Path) -> None:
    """A missing DB raises RuntimeError (not SystemExit), so it is called directly."""
    with pytest.raises(RuntimeError, match="No experiments database"):
        show_results(db_path=tmp_path / "absent.duckdb")
