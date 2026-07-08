"""`gptnt submission new` — build every leaderboard bundle from the DuckDB.

Everything derivable is stamped: identity + capabilities from the records, attribution from each
model's `PlayerIdentity`. Only the `submitter` block is written blank for the submitter to fill in,
and CI in the gptnt-submissions repo is the gate that checks it.
"""

from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from rich.console import Console

from gptnt.cli.submission._interactive import (
    gather_experiments_for_suite,
    group_experiments_by_model,
    load_suite,
    write_interactive_bundle,
)
from gptnt.cli.submission._statics import build_statics_submission
from gptnt.common.paths import Paths

paths = Paths()
console = Console()

# The canonical main-leaderboard set. Submitters override with --suite / --static for their own.
LEADERBOARD_SUITES: list[str] = ["multi-self-async", "multi-self-sync", "single-parametric-sync"]
LEADERBOARD_STATICS: list[str] = []


def _statics_runs(
    statics: list[str], statics_output_dir: Path, model: list[str]
) -> list[tuple[str, Path]]:
    """Every `(task, <task>_predictions/<model>/)` with run metadata passing the model filter."""
    return [
        (task, run_dir)
        for task in statics
        for run_dir in sorted((statics_output_dir / f"{task}_predictions").glob("*"))
        if (run_dir / "run_meta.json").exists() and (not model or run_dir.name in model)
    ]


def build_submission(
    experiments_db: Annotated[
        Path, Parameter(help="Path to the experiments.duckdb file.", env_var="EXPERIMENTS_DB")
    ] = paths.experiments_db,
    statics_output_dir: Annotated[
        Path,
        Parameter(help="Root holding <task>_predictions/<model>/.", env_var="STATICS_OUTPUTS"),
    ] = paths.output,
    output_dir: Annotated[
        Path, Parameter(help="Directory to write bundles into.", env_var="SUBMISSIONS_DIR")
    ] = paths.submissions,
    *,
    suites: Annotated[
        list[str], Parameter(name="--suite", help="Interactive suites to build (repeatable).")
    ] = LEADERBOARD_SUITES,
    statics: Annotated[
        list[str], Parameter(name="--static", help="Statics tasks to build (repeatable).")
    ] = LEADERBOARD_STATICS,
    model: Annotated[
        list[str] | None,
        Parameter(name="--model", help="Only build these models (default: every model present)."),
    ] = None,
) -> None:
    """Build every leaderboard bundle from the DuckDB; humans fill the blank fields afterwards."""
    built = 0
    for suite_name in suites:
        console.print(f"[bold]suite {suite_name}[/bold]")
        suite = load_suite(suite_name)
        experiments = gather_experiments_for_suite(experiments_db, suite, model)
        for _model_name, rows in group_experiments_by_model(experiments):
            write_interactive_bundle(rows, suite, output_dir)
            built += 1
    for task, run_dir in _statics_runs(statics, statics_output_dir, model or []):
        console.print(f"[bold]statics {task}[/bold]")
        build_statics_submission(run_dir, task, output_dir)
        built += 1

    console.print(f"Built {built} bundle(s) under {output_dir}.", style="bold")
    console.print("Fill in each submission.yaml's submitter, then submit to gptnt-submissions.")
