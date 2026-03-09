from pathlib import Path
from typing import Annotated

import structlog
import typer
from rich.console import Console
from wandb.apis.public import Runs

from gptnt.cli._fields import WandbEntityOption, WandbProjectOption
from gptnt.common.logger import create_progress
from gptnt.common.paths import Paths
from gptnt.experiments.wandb import get_runs_from_wandb

logger = structlog.get_logger()
console = Console()

paths = Paths()


def parse_experiment_outputs_from_directory(
    directory: Path, *, _uuid_length: int = 36
) -> set[tuple[str, str, Path]]:
    """Scan for experiment output files and extract (attempt_name, player_uuid, path) tuples."""
    experiments_to_check: set[tuple[str, str, Path]] = set()
    with create_progress() as progress:
        for path in progress.track(
            list(directory.rglob("experiment-*.json")), description="Scanning for experiment files"
        ):
            clean_file_name = path.stem.replace("experiment-", "")
            attempt_name = clean_file_name[: -_uuid_length - 1]  # remove trailing -{uuid}
            player_uuid = clean_file_name[-_uuid_length:]
            experiments_to_check.add((attempt_name, player_uuid, path))
    return experiments_to_check


def get_valid_wandb_runs_for_experiments(
    experiments_to_check: set[tuple[str, str, Path]], wandb_entity: str, wandb_project: str
) -> Runs:
    """Query WandB for valid runs matching the (attempt_name, player_uuid) pairs."""
    valid_wandb_runs = get_runs_from_wandb(
        f"{wandb_entity}/{wandb_project}",
        additional_filters=[
            {
                "$or": [
                    {
                        "$and": [
                            {"config.attempt_name": attempt_name},
                            {"config.player_uuid": player_uuid},
                        ]
                    }
                    for attempt_name, player_uuid, _ in experiments_to_check
                ]
            }
        ],
        per_page=1000,
        include_running=True,
    )
    return valid_wandb_runs


def get_experiment_outputs_to_delete(
    valid_wandb_runs: Runs, experiments_to_check: set[tuple[str, str, Path]]
) -> set[Path]:
    """Find experiment files that we want to delete."""
    pair_per_experiment_output = {
        (exp_name, player_uuid): path for exp_name, player_uuid, path in experiments_to_check
    }

    paths_to_keep = set()
    with create_progress(extra_fields=["extra"]) as progress:
        task = progress.add_task(
            "Checking experiments against valid WandB runs", total=len(valid_wandb_runs), extra=""
        )
        for run in valid_wandb_runs:
            exp_path = pair_per_experiment_output.get(
                (run.config["attempt_name"], run.config["player_uuid"])
            )

            if exp_path:
                paths_to_keep.add(exp_path)
            progress.update(
                task,
                advance=1,
                extra=f"[dim](paths to keep: {len(paths_to_keep)}/{len(experiments_to_check)})[/dim]",
            )

    paths_to_delete = {exp[2] for exp in experiments_to_check} - paths_to_keep
    return paths_to_delete


def delete_old_experiment_outputs(
    directory: Annotated[
        Path,
        typer.Argument(help="Directory containing experiment JSON files to delete.", exists=True),
    ] = paths.experiment_recorder,
    *,
    wandb_entity: WandbEntityOption,
    wandb_project: WandbProjectOption,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Only print files that would be deleted, without deleting them.",
            is_flag=True,
        ),
    ] = False,
) -> None:
    """Delete any experiment output files that are marked as invalid in WandB."""
    # 1. Scan for experiment output files and extract (attempt_name, player_uuid, path) tuples
    experiments_to_check = parse_experiment_outputs_from_directory(directory)
    if len(experiments_to_check) == 0:
        console.print(
            "[yellow]No experiment output files found. No files will be deleted.[/yellow]"
        )
        raise typer.Exit(code=0)

    console.print(
        f"Found {len(experiments_to_check)} experiment output files to check against WandB."
    )

    # 2. Query WandB for valid runs matching the (attempt_name, player_uuid) pairs
    valid_wandb_runs = get_valid_wandb_runs_for_experiments(
        experiments_to_check, wandb_entity, wandb_project
    )

    if len(valid_wandb_runs) == 0:
        console.print("[yellow]No valid runs found on WandB. No files will be deleted.[/yellow]")
        raise typer.Exit(code=0)

    console.print(
        f"Found {len(valid_wandb_runs)} valid runs on WandB from {len(experiments_to_check)} run outputs."
    )

    # 3. Find experiment files that we want to keep (so we can then know what to delete)
    paths_to_delete = get_experiment_outputs_to_delete(valid_wandb_runs, experiments_to_check)

    with create_progress() as progress:
        console.print(f"[red]{len(paths_to_delete)}[/red] invalid experiment outputs.")

        for path in progress.track(
            paths_to_delete, description="Deleting files", total=len(paths_to_delete)
        ):
            if dry_run:
                console.print(f"Would delete: {path}")
            else:
                path.unlink()
