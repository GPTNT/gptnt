from collections import defaultdict
from typing import Any

import structlog
import wandb
from pydantic import UUID4
from rich.progress import track
from wandb.apis.public import Run, Runs

logger = structlog.get_logger()

type CollatedRuns = dict[str, dict[UUID4, list[Run]]]


def get_runs_from_wandb(
    wandb_path: str,
    *,
    additional_filters: list[dict[str, Any]] | None = None,
    timeout: int | None = None,
) -> Runs:
    """Get runs from wandb API with specified filters."""
    additional_filters = additional_filters or []

    api = wandb.Api(timeout=timeout)
    runs = api.runs(
        wandb_path,
        filters={
            "$and": [
                {"state": "finished"},
                {"summary_metrics.is_hard_crash": False},
                {"summary_metrics.step": {"$gt": 1}},
                {"tags": {"$nin": ["old"]}},
                *additional_filters,
            ]
        },
    )
    logger.info(f"Found {len(runs)} runs on wandb", runs=len(runs), wandb_path=wandb_path)

    return runs


def collate_runs_per_experiment_per_game(runs: list[Run] | Runs) -> CollatedRuns:
    """Collate all the runs by experiments, and then by their game_id."""
    runs_per_experiment_per_game: CollatedRuns = defaultdict(lambda: defaultdict(list))
    for run in track(runs, description="Collating runs...", total=len(runs)):
        experiment_name: str = run.config["experiment_name"]
        game_id: UUID4 = run.config["game_id"]
        runs_per_experiment_per_game[experiment_name][game_id].append(run)
    return runs_per_experiment_per_game


def get_valid_experiments_from_collated_runs(collated_runs: CollatedRuns) -> list[str]:
    """Get valid experiment names from the collated runs."""
    valid_experiments = []
    for experiment_name, runs_per_game in track(
        collated_runs.items(), description="Filtering valid experiments..."
    ):
        # figure out if there should be one per game or two
        expected_num_players = 1 if "expert=None" in experiment_name else 2
        valid_games = [
            game_id
            for game_id, runs in runs_per_game.items()
            if all(game_run.summary.get("hard_crash", True) is False for game_run in runs)
            and all(game_run.state == "finished" for game_run in runs)
            and len(runs) == expected_num_players
        ]
        if valid_games:
            valid_experiments.append(experiment_name)

    return valid_experiments


def mark_invalid_games_as_old(collated_runs: CollatedRuns) -> None:
    """Mark invalid games as old from the collated runs."""
    counter = 0
    for experiment_name, runs_per_game in track(collated_runs.items()):
        expected_num_players = 1 if "expert=None" in experiment_name else 2
        for runs in runs_per_game.values():
            if len(runs) != expected_num_players:
                for run in runs:
                    run.tags.append("old")
                    run.update()
                    counter += 1

    logger.info(
        f"Marked {counter} runs as old due to invalid game conditions.", runs_marked=counter
    )


def mark_duplicate_runs_as_old(collated_runs: CollatedRuns) -> None:
    """Mark duplicate games/runs as old."""
    counter = 0
    for runs_per_game in track(collated_runs.values()):
        if len(runs_per_game) <= 1:
            continue
        # sort all the games by their creation data
        ordered_games = sorted(runs_per_game.items(), key=lambda game: game[1][0].created_at)
        # Keep the runs for the latest game, and mark the rest as old
        runs_to_delete = [run for game in ordered_games[:-1] for run in game[1]]

        for run in runs_to_delete:
            run.tags.append("old")
            run.update()
            counter += 1
    logger.info(f"Marked {counter} runs as old due to duplicates.", runs_marked=counter)
