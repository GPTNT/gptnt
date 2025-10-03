from pathlib import Path
from typing import Annotated

import anyio
import httpx
import typer
from rich.console import Console
from structlog import get_logger

from gptnt.common.paths import Paths
from gptnt.entrypoints._async_typer import AsyncTyper
from gptnt.entrypoints.run_experiment_manager import EM_PORT
from gptnt.experiments.experiments import ExperimentSpec
from gptnt.experiments.wandb import (
    collate_runs_per_experiment_per_game,
    get_runs_from_wandb,
    get_valid_experiments_from_collated_runs,
)

logger = get_logger()
paths = Paths()
console = Console()


app = AsyncTyper(help="Throw AI experiments to the experiment queue.", no_args_is_help=True)


async def _send_experiments(experiments: list[ExperimentSpec]) -> None:
    """Send the experiments to the experiment specs queue."""
    async with httpx.AsyncClient() as client:
        _ = await client.post(
            f"http://127.0.0.1:{EM_PORT}/add-specs",
            json={"specs": [experiment.model_dump(mode="json") for experiment in experiments]},
        )


def _filter_experiments(  # noqa: WPS210
    loaded_experiments: list[ExperimentSpec], *, wandb_path: str
) -> list[ExperimentSpec]:
    """Filter the experiments by those already run on wandb."""
    loaded_experiment_names = (experiment.experiment_name for experiment in loaded_experiments)

    with console.status("Checking for existing runs on wandb..."):
        wandb_runs = get_runs_from_wandb(
            wandb_path,
            additional_filters=[
                {"$or": [{"config.experiment_name": name} for name in loaded_experiment_names]}
            ],
        )

        # If there are no runs, return all loaded experiments
        if len(wandb_runs) == 0:
            logger.info("No existing runs found on wandb, throwing all experiments.")
            return loaded_experiments

    runs_per_experiment_per_game = collate_runs_per_experiment_per_game(wandb_runs)
    valid_experiments = get_valid_experiments_from_collated_runs(runs_per_experiment_per_game)
    invalid_experiments: list[ExperimentSpec] = [
        experiment
        for experiment in loaded_experiments
        if experiment.experiment_name not in valid_experiments
    ]
    logger.info(
        f"{len(invalid_experiments)} experiments to throw",
        invalid=len(invalid_experiments),
        valid=len(valid_experiments),
    )
    return invalid_experiments


@app.command()
async def throw_ai_experiments(
    *,
    experiments_dir: Annotated[Path, typer.Option(help="Path to experiments")] = paths.experiments,
    wandb_path: Annotated[str, typer.Option(help="Wandb entity/project path")] = "gptnt/for-real",
    dry_run: Annotated[
        bool, typer.Option(help="If set, only logs the experiments that would be thrown")
    ] = False,
    skip_wandb: Annotated[
        bool, typer.Option(help="If set, skips checking wandb for existing runs")
    ] = False,
    delete_unneeded: Annotated[
        bool, typer.Option(help="If set, deletes any unneeded experiments")
    ] = False,
) -> None:
    """Throw the AI experiments."""
    if dry_run:
        logger.warning("Dry run mode is enabled. No experiments will be thrown.")

    experiment_paths = list(experiments_dir.rglob("*.json"))

    # Load the experiments from the dir
    loaded_experiments = [
        ExperimentSpec.model_validate_json(experiment_path.read_bytes())
        for experiment_path in experiment_paths
    ]

    if not loaded_experiments:
        logger.warning("No experiments found in the directory.")
        return
    logger.info(f"Loaded {len(loaded_experiments)} experiments from '{experiments_dir}'")

    if skip_wandb:
        logger.warning("Skipping wandb check for existing runs.")
    else:
        # Filter the experiments by those already run on wandb
        loaded_experiments = _filter_experiments(loaded_experiments, wandb_path=wandb_path)

    if delete_unneeded:
        all_experiment_names = [experiment.experiment_name for experiment in loaded_experiments]
        for path in experiment_paths:
            if path.stem not in all_experiment_names:
                path.unlink(missing_ok=True)

    if not dry_run:
        await _send_experiments(loaded_experiments)
        logger.info("All experiments thrown.")


if __name__ == "__main__":
    # configure_logging()

    anyio.run(app())
