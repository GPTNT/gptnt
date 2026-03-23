import itertools
from pathlib import Path

import duckdb
from rich.progress import Progress
from wandb.apis.public import Run

from gptnt.common.logger import ProgressSentinel, with_default_progress
from gptnt.experiments.wandb import get_runs_from_wandb
from gptnt.records.models import ExperimentMetadata


@with_default_progress()
def get_all_experiments_from_db(
    db_path: Path, *, progress: Progress = ProgressSentinel
) -> list[ExperimentMetadata]:
    """Get all experiments from the DuckDB file."""
    task = progress.add_task("Fetching all experiments from DuckDB", total=None)

    with duckdb.connect(str(db_path)) as conn:
        output = conn.execute("SELECT * FROM experiment_metadata")
        columns = [desc[0] for desc in output.description]
        experiments = [
            ExperimentMetadata.model_validate(dict(zip(columns, row, strict=False)))
            for row in output.fetchall()
        ]

    progress.update(task, total=len(experiments), completed=len(experiments))
    return experiments


@with_default_progress()
def get_non_validated_experiments_from_db(
    db_path: Path, *, progress: Progress = ProgressSentinel
) -> list[ExperimentMetadata]:
    """Get all experiments from the DuckDB file that haven't been validated yet."""
    task = progress.add_task("Fetching non-validated experiments from DuckDB", total=None)

    with duckdb.connect(str(db_path)) as conn:
        output = conn.execute("SELECT * FROM experiment_metadata WHERE is_valid IS NULL")
        columns = [desc[0] for desc in output.description]
        candidates = [
            ExperimentMetadata.model_validate(dict(zip(columns, row, strict=False)))
            for row in output.fetchall()
        ]

    if not candidates:
        progress.console.print("[green]✓[/green]  All experiments already have is_valid set.")

    progress.update(task, total=len(candidates), completed=len(candidates))
    return candidates


@with_default_progress(extra_fields=["extra"])
def _get_known_valid_runs_from_wandb(
    scanned_experiments: list[ExperimentMetadata],
    wandb_path: str,
    *,
    progress: Progress = ProgressSentinel,
) -> list[Run]:
    """Get all runs from WandB that match the known experiment attempt names and player UUIDs."""
    task = progress.add_task("Fetching runs from WandB", total=None)

    experiment_conditions = [
        {
            "$and": [
                {"config.attempt_name": exp.attempt_name},
                {
                    "config.player_uuid": {
                        "$in": [str(uuid) for uuid in (exp.player_uuids or []) if uuid]
                    }
                },
            ]
        }
        for exp in scanned_experiments
        if any(uuid for uuid in (exp.player_uuids or []))
    ]

    wandb_runs = []
    for chunk in itertools.batched(experiment_conditions, 1000, strict=False):
        chunk_runs = get_runs_from_wandb(
            wandb_path, timeout=120, additional_filters=[{"$or": chunk}], per_page=1000
        )
        wandb_runs.extend(chunk_runs)
        progress.update(task, total=None, completed=len(wandb_runs))
    progress.update(task, total=len(wandb_runs), completed=len(wandb_runs))

    return wandb_runs


@with_default_progress(extra_fields=["extra"])
def validate_experiments_against_wandb(
    scanned_experiments: list[ExperimentMetadata],
    wandb_path: str,
    *,
    progress: Progress = ProgressSentinel,
) -> list[ExperimentMetadata]:
    """Validate the scanned experiments against WandB."""
    wandb_runs = _get_known_valid_runs_from_wandb(
        scanned_experiments, wandb_path, progress=progress
    )

    if not wandb_runs:
        return []

    valid_attempt_player_pairs: set[tuple[str, str]] = set()
    for run in progress.track(
        wandb_runs, description="Extracting metadata from runs", total=len(wandb_runs)
    ):
        valid_attempt_player_pairs.add((run.config["attempt_name"], run.config["player_uuid"]))

    task = progress.add_task(
        "Validating experiments against WandB", total=len(scanned_experiments)
    )
    valid_scanned_experiments = []
    for experiment in scanned_experiments:
        assert experiment.player_uuids is not None
        is_valid = all(
            (experiment.attempt_name, str(uuid)) in valid_attempt_player_pairs
            for uuid in experiment.player_uuids
        )
        experiment.is_valid = is_valid
        if is_valid:
            valid_scanned_experiments.append(experiment)
        progress.update(
            task, advance=1, extra=f"[dim](valid: {len(valid_scanned_experiments)})[/dim]"
        )

    return valid_scanned_experiments


@with_default_progress()
def update_db_with_validation_results(
    valid_experiments: list[ExperimentMetadata],
    db_path: Path,
    *,
    progress: Progress = ProgressSentinel,
) -> None:
    """Update the DuckDB file with the validation results."""
    task = progress.add_task(
        "Updating DuckDB with validation results", total=len(valid_experiments)
    )

    with duckdb.connect(str(db_path)) as conn:
        for experiment in valid_experiments:
            _ = conn.execute(
                "UPDATE experiment_metadata SET is_valid = ? WHERE attempt_name = ?",
                [experiment.is_valid, experiment.attempt_name],
            )
            progress.advance(task)
