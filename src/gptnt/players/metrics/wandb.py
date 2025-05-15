from typing import Any, cast

import wandb
from pandas import json_normalize
from pydantic import ValidationError
from rich.progress import track
from structlog import get_logger
from unflatten import unflatten

from gptnt.experiments.experiments import ExperimentSpec

_logger = get_logger()


def flatten_dict(config: dict[str, Any], *, separator: str = ".") -> dict[str, Any]:
    """Flatten dictionaries to dot notation."""
    # Although this flattens it, it creates a dataframe for the output
    normalized_config = json_normalize(config, sep=separator)

    # Convert the dataframe which only has a single row into the output format we want
    flattened_config_as_dict = normalized_config.to_dict(orient="records")[0]
    return cast("dict[str, Any]", flattened_config_as_dict)


def check_if_experiments_on_wandb(
    *, experiments: set[ExperimentSpec], wandb_entity: str, wandb_project: str
) -> set[ExperimentSpec]:
    """Checks if the experiments are already on wandb.

    This is used to prevent duplicate experiments from being run.
    """
    # Extract all the experiment names
    experiment_names = [
        {"config.experiment_name": experiment.experiment_name} for experiment in experiments
    ]
    wandb_runs = wandb.Api().runs(
        path=f"{wandb_entity}/{wandb_project}",
        filters={
            "$and": [
                {"state": "finished"},
                {"$or": experiment_names},
                {"summary_metrics.hard_crash": False},
            ]
        },
    )

    _logger.info(
        "Checking for existing runs on wandb using experiment names. This might take a while...",
        entity=wandb_entity,
        project=wandb_project,
    )
    _logger.info(
        "Found existing runs on wandb",
        runs=len(wandb_runs),
        entity=wandb_entity,
        project=wandb_project,
    )
    if wandb_runs.length == 0:
        return experiments

    wandb_spec_set: set[ExperimentSpec] = set()
    for run in track(
        wandb_runs, description="Checking for completed runs", total=wandb_runs.length
    ):
        unflattened_config = unflatten(run.config)
        try:
            myspec = ExperimentSpec.model_validate(unflattened_config)
        except ValidationError as _:
            _logger.warning(f"Could not parse config {run.config}.")
            continue
        wandb_spec_set.add(myspec)

    return experiments - wandb_spec_set
