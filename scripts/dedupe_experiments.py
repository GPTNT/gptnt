from gptnt.experiments.wandb import (
    collate_runs_per_experiment_per_game,
    get_runs_from_wandb,
    mark_duplicate_runs_as_old,
    mark_invalid_games_as_old,
)


def dedupe_experiments(wandb_path: str) -> None:
    """Deduplicate runs that we've run several times.

    We are making the decision to keep the latest run for each experiment and removing the older
    ones.
    """
    runs = get_runs_from_wandb(wandb_path)
    collated_runs = collate_runs_per_experiment_per_game(runs)
    mark_invalid_games_as_old(collated_runs)
    mark_duplicate_runs_as_old(collated_runs)


if __name__ == "__main__":
    dedupe_experiments(wandb_path="gptnt/for-real")
