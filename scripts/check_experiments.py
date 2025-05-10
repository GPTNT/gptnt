import os

import wandb
from pydantic import ValidationError
from rich.progress import track
from unflatten import unflatten

from gptnt.common.paths import Paths
from gptnt.ktane.experiments.experiments import ExperimentSpec

paths = Paths()


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

    wandb_spec_set: set[ExperimentSpec] = set()

    for run in track(
        wandb_runs, description="Checking for completed runs", total=wandb_runs.length
    ):
        unflattened_config = unflatten(run.config)
        try:
            myspec = ExperimentSpec.model_validate(unflattened_config)
        except ValidationError as _:
            print(f"Could not parse config {run.config}.")  # noqa: T201
            continue
        wandb_spec_set.add(myspec)

    return wandb_spec_set


def get_duplicate_experiments() -> set[ExperimentSpec]:
    """Get the duplicate experiments from the wandb API."""
    experiments = {
        ExperimentSpec.model_validate_json(path.read_text())
        for path in paths.experiments.rglob("*.json")
    }

    return check_if_experiments_on_wandb(
        experiments=experiments,
        wandb_entity=os.getenv("WANDB_ENTITY", "gptnt"),
        wandb_project=os.getenv("WANDB_PROJECT", "gptnt"),
    )


def main() -> None:
    duplicate_experiments = get_duplicate_experiments()
    print(f"Found {len(duplicate_experiments)} duplicate experiments on wandb.")  # noqa: T201


if __name__ == "__main__":
    main()
