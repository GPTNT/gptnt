from pathlib import Path
from typing import Annotated

import anyio
import httpx
import typer
from rich.console import Console
from structlog import get_logger

from gptnt.common.async_typer import AsyncTyper
from gptnt.common.paths import Paths
from gptnt.entrypoints.run_experiment_manager import EM_PORT
from gptnt.experiments.experiments import ExperimentSpec
from gptnt.experiments.wandb import (
    collate_runs_per_experiment_per_game,
    get_invalid_runs_from_collated_runs,
    get_runs_from_wandb,
    mark_runs_as_old,
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


def filter_experiments(  # noqa: WPS210
    loaded_experiments: list[ExperimentSpec], *, wandb_path: str
) -> list[ExperimentSpec]:
    """Filter the experiments by those already run on wandb."""
    # Get all the experiment name for the files we have on disk
    loaded_experiment_names = (experiment.experiment_name for experiment in loaded_experiments)

    # Get all the runs from wandb with these experiments (if they exist)
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

    # Collate the runs into an experiment
    runs_per_experiment_per_game = collate_runs_per_experiment_per_game(wandb_runs)

    logger.info(f"{len(wandb_runs)} runs --> {len(runs_per_experiment_per_game)} experiments.")

    # For the ones we pulled from wandb, check if they are invalid and need tagging
    invalid_runs = get_invalid_runs_from_collated_runs(runs_per_experiment_per_game)
    if invalid_runs:
        logger.warning(f"Found {len(invalid_runs)} invalid runs on wandb. Adding the 'old' tag")
        mark_runs_as_old(invalid_runs)

    invalid_experiment_names = {run.config["experiment_name"] for run in invalid_runs}
    invalid_experiments_on_wandb = [
        spec for spec in loaded_experiments if spec.experiment_name in invalid_experiment_names
    ]

    specs_not_on_wandb = [
        experiment
        for experiment in loaded_experiments
        if experiment.experiment_name not in runs_per_experiment_per_game
        and experiment.experiment_name not in invalid_experiment_names
    ]

    # For every experiment in the spec list, if there is a run on wandb that is valid, we should
    # NOT throw it.
    specs_to_throw = [*specs_not_on_wandb, *invalid_experiments_on_wandb]

    logger.info(
        f"{len(specs_to_throw)} experiments to throw",
        invalid=len(invalid_experiments_on_wandb),
        missing=len(specs_not_on_wandb),
        filtered_out=len(loaded_experiments) - len(specs_to_throw),
    )
    return specs_to_throw


@app.command()
async def throw_ai_experiments(
    *,
    experiments_dir: Annotated[Path, typer.Option(help="Path to experiments")] = paths.experiments,
    wandb_entity: Annotated[
        str, typer.Option(help="Wandb entity (user or team) name", envvar="WANDB_ENTITY")
    ],
    wandb_project: Annotated[str, typer.Option(help="Wandb project name", envvar="WANDB_PROJECT")],
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
        loaded_experiments = filter_experiments(
            loaded_experiments, wandb_path=f"{wandb_entity}/{wandb_project}"
        )

    if delete_unneeded:
        all_experiment_names = [experiment.experiment_name for experiment in loaded_experiments]
        for path in experiment_paths:
            if path.stem not in all_experiment_names:
                path.unlink(missing_ok=True)

    if not dry_run:
        await _send_experiments(loaded_experiments)
        logger.info("All experiments thrown.")


if __name__ == "__main__":
    anyio.run(app())
