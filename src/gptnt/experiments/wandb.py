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
                # {"summary_metrics.is_hard_crash": False},
                # {"summary_metrics.step": {"$gt": 1}},
                {"tags": {"$nin": ["old"]}},
                *additional_filters,
            ]
        },
    )
    logger.info(f"Found {len(runs)} runs on wandb", runs=len(runs), wandb_path=wandb_path)

    return runs


def collate_runs_per_experiment_per_game(runs: list[Run] | Runs) -> CollatedRuns:
    """Collate all the runs by experiments, and then by their session_id."""
    runs_per_experiment_per_game: CollatedRuns = defaultdict(lambda: defaultdict(list))
    for run in track(runs, description="Collating runs...", total=len(runs)):
        experiment_name: str = run.config["experiment_name"]
        session_id: UUID4 = run.config["session_id"]
        runs_per_experiment_per_game[experiment_name][session_id].append(run)
    return runs_per_experiment_per_game


def has_run_falsely_finished(run: Run) -> bool:
    """Check if a run has false-ly finished successfully.

    This happens when the run crashes or the services are shut down mid-run, which means we need to
    check for a fix them.
    """
    # Ignore if not defuser
    if run.config["role"] != "defuser":
        return False
    return bool(
        "is_solved" in run.summary  # noqa: WPS222
        and "is_hard_crash" in run.summary
        and "is_timed_out" in run.summary
        and "is_strike_out" in run.summary
        and run.summary["is_solved"] is False
        and run.summary["is_hard_crash"] is False
        and run.summary["is_timed_out"] is False
        and run.summary["is_strike_out"] is False
    )


def is_run_valid(run: Run) -> bool:
    """Check if a run is valid."""
    return (
        # If the key is not in the summary, the its not valid
        "is_hard_crash" in run.summary
        # Make sure it's not false
        and run.summary.get("is_hard_crash", False) is False
        # make sure the run is finished
        and run.state == "finished"
        and not has_run_falsely_finished(run)
    )


def get_invalid_runs_from_collated_runs(collated_runs: CollatedRuns) -> list[Run]:
    """Get invalid run names from the collated runs."""
    invalid_runs = []
    for experiment_name, runs_per_game in track(
        collated_runs.items(), description="Checking for invalid runs..."
    ):
        expected_num_players = 1 if "expert=None" in experiment_name else 2
        invalid_games = [
            session_id
            for session_id, runs in runs_per_game.items()
            if not (len(runs) == expected_num_players and all(is_run_valid(run) for run in runs))
        ]
        for session_id in invalid_games:
            invalid_runs.extend(runs_per_game[session_id])
    return invalid_runs


def get_valid_experiments_from_collated_runs(collated_runs: CollatedRuns) -> list[str]:
    """Get valid experiment names from the collated runs."""
    valid_experiments = []
    for experiment_name, runs_per_game in track(
        collated_runs.items(), description="Filtering valid experiments..."
    ):
        # figure out if there should be one per game or two
        expected_num_players = 1 if "expert=None" in experiment_name else 2
        valid_games = [
            session_id
            for session_id, runs in runs_per_game.items()
            if all(is_run_valid(game_run) for game_run in runs)
            and len(runs) == expected_num_players
        ]
        if valid_games:
            valid_experiments.append(experiment_name)

    return valid_experiments


def mark_runs_as_old(runs: list[Run]) -> None:
    """Mark the runs as old by adding the 'old' tag."""
    for run in track(runs, description="Marking runs as old...", total=len(runs)):
        run.tags.append("old")
        run.update()


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
