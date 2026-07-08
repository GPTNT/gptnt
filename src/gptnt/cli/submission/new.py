"""`gptnt submission new` — build every leaderboard bundle from the DuckDB.

Everything derivable is stamped: identity + capabilities from the records, attribution from each
model's `PlayerIdentity`. Only the `submitter` block is written blank for the submitter to fill in.
"""

import itertools
from pathlib import Path
from typing import Annotated

import structlog
from cyclopts import Parameter
from pydantic import ValidationError
from rich.console import Console

from gptnt.cli.submission._bundle import InteractiveBundle, StaticsBundle
from gptnt.cli.submission._interactive import (
    gather_experiments_for_suite,
    group_experiments_by_model,
)
from gptnt.common.paths import Paths
from gptnt.experiments.generation.pipeline import compose_suite
from gptnt.statics.run_metadata import StaticsRunMetadata

logger = structlog.get_logger()

paths = Paths()
console = Console()

# The canonical main-leaderboard set. Submitters override with --suite / --static for their own.
LEADERBOARD_SUITES: list[str] = ["multi-self-async", "multi-self-sync", "single-parametric-sync"]
LEADERBOARD_STATICS: list[str] = []


def _load_run_metadata_for_static(run_dir: Path) -> StaticsRunMetadata | None:
    """Return parsed metadata for run_dir, or None (with a warning) on any failure."""
    try:
        return StaticsRunMetadata.model_validate_json((run_dir / "run_meta.json").read_text())
    except (FileNotFoundError, ValidationError) as exc:
        logger.warning(f"Skipping {run_dir}", reason=str(exc), exc_info=exc)
        return None


def _statics_runs(
    *, statics: list[str], statics_output_dir: Path, model_filter: set[str]
) -> list[tuple[Path, StaticsRunMetadata]]:
    """Every `(run_dir, metadata)` with a parseable `run_meta.json` passing the model filter.

    Matches on `capabilities.player_name`. Runs whose `run_meta.json` is missing or unparsable are
    skipped.
    """
    all_run_dirs = itertools.chain.from_iterable(
        statics_output_dir.glob(f"{task}_predictions/*") for task in statics
    )

    runs: list[tuple[Path, StaticsRunMetadata]] = [
        (run_dir, meta)
        for run_dir in all_run_dirs
        if (meta := _load_run_metadata_for_static(run_dir)) is not None
        and (not model_filter or meta.capabilities.player_name in model_filter)
    ]
    return runs


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
    """Build every submission bundle from the DuckDB."""
    built = 0

    for suite_name in suites:
        console.print(f"[bold]suite {suite_name}[/bold]")
        suite = compose_suite(suite_name)
        experiments = gather_experiments_for_suite(experiments_db, suite, model)
        for _, model_experiments in group_experiments_by_model(experiments):
            _ = InteractiveBundle.from_experiments(model_experiments, suite).save(output_dir)
            built += 1

    for run_dir, metadata in _statics_runs(
        statics=statics, statics_output_dir=statics_output_dir, model_filter=set(model or [])
    ):
        console.print(f"[bold]statics {metadata.statics.task_name}[/bold]")
        _ = StaticsBundle.from_run_dir(run_dir, metadata=metadata).save(output_dir)
        built += 1

    console.print(f"Built {built} bundle(s) under {output_dir}.", style="bold")
    console.print("Fill in each submission.yaml's submitter, then submit to gptnt-submissions.")
