from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console
from structlog import get_logger

from gptnt.core.common.cli_options import WandbEntityOption, WandbProjectOption
from gptnt.core.common.paths import Paths

if TYPE_CHECKING:
    from gptnt.core.experiments.experiments import ExperimentSpec
    from gptnt.records.wandb_runs import CollatedRuns

logger = get_logger()
paths = Paths()
console = Console()


async def _send_experiments(experiments: list[ExperimentSpec]) -> None:
    """Send the experiments to the experiment specs queue."""
    import httpx

    from gptnt.interactive.entrypoints.run_experiment_manager import EM_PORT

    async with httpx.AsyncClient() as client:
        _ = await client.post(
            f"http://127.0.0.1:{EM_PORT}/add-specs",
            json={"specs": [experiment.model_dump(mode="json") for experiment in experiments]},
        )


def _gather_and_collate(attempt_names: list[str], wandb_path: str) -> CollatedRuns | None:
    """Gather and collate runs from WandB."""
    from gptnt.records.wandb_runs import collate_runs_per_experiment_per_game, get_runs_from_wandb

    with console.status("Checking for existing runs on wandb..."):
        wandb_runs = get_runs_from_wandb(
            wandb_path,
            additional_filters=[
                {"$or": [{"config.attempt_name": name} for name in attempt_names]}
            ],
            per_page=1000,
        )
        if len(wandb_runs) == 0:
            return None

    # Collate the runs into an experiment
    collated_runs = collate_runs_per_experiment_per_game(wandb_runs)
    logger.info(f"{len(wandb_runs)} runs --> {len(collated_runs)} experiments.")
    return collated_runs


def filter_experiments(  # noqa: WPS210
    loaded_experiments: list[ExperimentSpec], *, wandb_path: str
) -> list[ExperimentSpec]:
    """Filter the experiments by those already run on wandb."""
    from gptnt.records.cli.cleanup import cleanup_wandb_runs

    # Get all the attempt names for the files we have on disk
    loaded_attempt_names = [experiment.attempt_name for experiment in loaded_experiments]

    collated_runs = _gather_and_collate(loaded_attempt_names, wandb_path)
    if collated_runs is None:
        logger.info("No existing runs found on wandb, throwing all experiments.")
        return loaded_experiments

    # Cleanup now
    cleanup_wandb_runs(collated_runs)

    # and re-gather again
    collated_runs = _gather_and_collate(loaded_attempt_names, wandb_path)
    if collated_runs is None:
        logger.info("No existing runs found on wandb, throwing all experiments.")
        return loaded_experiments

    # For every experiment in the spec list, if there is a run on wandb that is valid, we should
    # NOT throw it.
    specs_not_on_wandb = [
        experiment
        for experiment in loaded_experiments
        if experiment.attempt_name not in collated_runs
    ]

    logger.info(
        f"{len(specs_not_on_wandb)} experiments to throw",
        missing=len(specs_not_on_wandb),
        filtered_out=len(loaded_experiments) - len(specs_not_on_wandb),
    )
    return specs_not_on_wandb


async def send_experiment_specs_to_em(
    *,
    experiments_dir: Annotated[Path, typer.Option(help="Path to experiments")] = paths.experiments,
    wandb_entity: WandbEntityOption,
    wandb_project: WandbProjectOption,
    dry_run: Annotated[
        bool, typer.Option(help="If set, only logs the experiments that would be thrown")
    ] = False,
    skip_wandb: Annotated[
        bool, typer.Option(help="If set, skips checking wandb for existing runs")
    ] = False,
    delete_unneeded: Annotated[
        bool, typer.Option(help="If set, deletes any unneeded experiment specs from the directory")
    ] = False,
) -> None:
    """Send the experiment specs to the EM queue."""
    from gptnt.core.experiments.experiments import ExperimentSpec

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
        all_names = [experiment.attempt_name for experiment in loaded_experiments]
        for path in experiment_paths:
            if path.stem not in all_names:
                path.unlink(missing_ok=True)

    if not dry_run:
        await _send_experiments(loaded_experiments)
        logger.info("All experiments thrown.")
