from collections import defaultdict
from pathlib import Path
from typing import Any

import structlog
import wandb
from pydantic import UUID4
from rich.progress import Progress, track
from wandb.apis.public import Run, Runs

from gptnt.common.logger import ProgressSentinel, with_default_progress

logger = structlog.get_logger()

type CollatedRuns = dict[str, dict[UUID4, list[Run]]]


def get_runs_from_wandb(
    wandb_path: str,
    *,
    additional_filters: list[dict[str, Any]] | None = None,
    timeout: int | None = None,
    per_page: int = 100,
    include_running: bool = False,
    include_old: bool = False,
) -> Runs:
    """Get runs from wandb API with specified filters."""
    additional_filters = list(additional_filters or [])
    if not include_old:
        additional_filters.append({"tags": {"$nin": ["old"]}})

    states = ["running", "finished"] if include_running else ["finished"]
    api = wandb.Api(timeout=timeout)
    runs = api.runs(
        wandb_path,
        filters={
            "$and": [
                {"state": {"$in": states}},
                # {"summary_metrics.is_hard_crash": False},
                # {"summary_metrics.step": {"$gt": 1}},
                *additional_filters,
            ]
        },
        per_page=per_page,
    )
    logger.info(
        f"Found {len(runs)} runs (not experiments) on wandb", runs=len(runs), wandb_path=wandb_path
    )

    return runs


@with_default_progress(extra_fields=["extra"])
def collate_runs_per_experiment_per_game(
    runs: list[Run] | Runs, *, progress: Progress = ProgressSentinel
) -> CollatedRuns:
    """Collate all the runs by experiments, and then by their session_id."""
    runs_per_experiment_per_game: CollatedRuns = defaultdict(lambda: defaultdict(list))
    task = progress.add_task("Collating: run → session → experiment", total=len(runs))
    session_ids_seen = set()

    for run in runs:
        attempt_name: str = run.config["attempt_name"]
        session_id: UUID4 = run.config["session_id"]
        runs_per_experiment_per_game[attempt_name][session_id].append(run)
        session_ids_seen.add(session_id)
        progress.update(
            task,
            advance=1,
            extra=f"[dim](experiments: {len(runs_per_experiment_per_game)}; sessions: {len(session_ids_seen)})[/dim]",
        )
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
        and run.summary.get("is_hard_crash", True) is False
        # make sure the run is finished
        and run.state == "finished"
        and not has_run_falsely_finished(run)
    )


def mark_runs_as_old(runs: list[Run]) -> None:
    """Mark the runs as old by adding the 'old' tag."""
    for run in track(runs, description="Marking runs as old...", total=len(runs)):
        run.tags.append("old")
        run.update()


@with_default_progress(extra_fields=["extra"])
def mark_mismatched_player_games_as_old(
    collated_runs: CollatedRuns, *, progress: Progress = ProgressSentinel, dry_run: bool = False
) -> None:
    """Mark games with mismatched player counts as old from the collated runs."""
    counter = 0
    task = progress.add_task("Flagging mismatched runs", total=len(collated_runs), extra="")
    for attempt_name, runs_per_game in collated_runs.items():
        expected_num_players = 1 if "expert=None" in attempt_name else 2
        mismatched_games = [
            run
            for runs in runs_per_game.values()
            if len(runs) != expected_num_players
            for run in runs
        ]
        for run in mismatched_games:
            if dry_run:
                progress.console.print(
                    f"[dim][Mismatched Player Count] attempt: {attempt_name}, run: {run.name}[/dim]"
                )
            else:
                run.tags.append("old")
                run.update()
            counter += 1
        progress.update(task, advance=1, extra=f"[dim](mismatched runs: {counter})[/dim]")


@with_default_progress(extra_fields=["extra"])
def mark_duplicate_runs_as_old(
    collated_runs: CollatedRuns, *, progress: Progress = ProgressSentinel, dry_run: bool = False
) -> None:
    """Mark duplicate games/runs as old."""
    counter = 0
    task = progress.add_task("Flagging duplicates", total=len(collated_runs), extra="")
    for runs_per_game in collated_runs.values():
        if len(runs_per_game) > 1:
            # sort all the games by their creation data
            ordered_games = sorted(runs_per_game.items(), key=lambda game: game[1][0].created_at)
            # Keep the runs for the latest game, and mark the rest as old
            runs_to_delete = [run for game in ordered_games[:-1] for run in game[1]]

            for run in runs_to_delete:
                if dry_run:
                    progress.console.print(
                        f"[dim][Duplicate Run] attempt: {run.config['attempt_name']}, session: {run.config['session_id']}, run: {run.name}[/dim]"
                    )
                else:
                    run.tags.append("old")
                    run.update()
                counter += 1

        progress.update(task, advance=1, extra=f"[dim](duplicate runs: {counter})[/dim]")


@with_default_progress(extra_fields=["extra"])
def mark_falsely_finished_as_old(
    collated_runs: CollatedRuns, *, progress: Progress = ProgressSentinel, dry_run: bool = False
) -> None:
    """Mark runs that have falsely finished as old.

    If one run is falsely finished, then all runs for that session should be marked as old since
    the experiment is not valid.
    """
    counter = 0
    task = progress.add_task("Flagging falsely finished runs", total=len(collated_runs), extra="")
    for runs_per_game in collated_runs.values():
        games_with_falsely_finished_runs = [
            session_id
            for session_id, runs in runs_per_game.items()
            if any(has_run_falsely_finished(run) for run in runs)
        ]
        runs_to_mark_old = [
            run
            for session_id in games_with_falsely_finished_runs
            for run in runs_per_game[session_id]
        ]

        for run in runs_to_mark_old:
            if dry_run:
                progress.console.print(
                    f"[dim][Falsely Finished Run] attempt: {run.config['attempt_name']}, session: {run.config['session_id']}, run: {run.name}[/dim]"
                )
            else:
                run.tags.append("old")
                run.update()
            counter += 1

        progress.update(task, advance=1, extra=f"[dim](falsely-finished runs: {counter})[/dim]")


@with_default_progress()
def parse_experiment_outputs_from_directory(
    directory: Path, *, progress: Progress = ProgressSentinel, _uuid_length: int = 36
) -> set[tuple[str, str, Path]]:
    """Scan for experiment output files and extract (attempt_name, player_uuid, path) tuples."""
    experiments_to_check: set[tuple[str, str, Path]] = set()
    for path in progress.track(
        list(directory.rglob("experiment-*.json")), description="Scanning output files"
    ):
        clean_file_name = path.stem.replace("experiment-", "")
        attempt_name = clean_file_name[: -_uuid_length - 1]  # remove trailing -{uuid}
        player_uuid = clean_file_name[-_uuid_length:]
        experiments_to_check.add((attempt_name, player_uuid, path))
    return experiments_to_check


@with_default_progress(extra_fields=["extra"])
def mark_runs_without_output_files_as_old(
    runs: list[Run] | Runs,
    experiment_outputs: set[tuple[str, str, Path]],
    *,
    progress: Progress = ProgressSentinel,
    dry_run: bool = False,
) -> None:
    """Mark runs as old if they don't have a corresponding output file."""
    task = progress.add_task("Flagging runs missing output files", total=len(runs), extra="")

    pair_per_experiment_output = {
        (attempt_name, player_uuid): path for attempt_name, player_uuid, path in experiment_outputs
    }
    counter = 0
    for run in runs:
        experiment_path = pair_per_experiment_output.get(
            (run.config["attempt_name"], run.config["player_uuid"])
        )
        if experiment_path is None:
            counter += 1
            if dry_run:
                progress.console.print(
                    f"[dim][Missing Output File] attempt: {run.config['attempt_name']}, session: {run.config['session_id']}, run: {run.name}[/dim]"
                )
            else:
                run.tags.append("old")
                run.update()

        progress.update(
            task, advance=1, extra=f"[dim](missing output files: {counter}/{len(runs)})[/dim]"
        )


@with_default_progress(extra_fields=["extra"])
def delete_old_experiment_outputs(
    valid_wandb_runs: list[Run] | Runs,
    experiments_to_check: set[tuple[str, str, Path]],
    *,
    progress: Progress = ProgressSentinel,
    dry_run: bool = False,
) -> None:
    """Delete any experiment file that is not valid on WandB."""
    pair_per_experiment_output = {
        (exp_name, player_uuid): path for exp_name, player_uuid, path in experiments_to_check
    }

    task = progress.add_task(
        "Checking outputs without valid WandB runs", total=len(valid_wandb_runs)
    )
    files_to_keep: set[Path] = set()
    for run in valid_wandb_runs:
        exp_path = pair_per_experiment_output.get(
            (run.config["attempt_name"], run.config["player_uuid"])
        )

        if exp_path:
            files_to_keep.add(exp_path)

        progress.update(
            task,
            advance=1,
            extra=f"[dim](to keep: {len(files_to_keep)}, estimated to delete: {len(experiments_to_check) - len(files_to_keep)})[/dim]",
        )

    files_to_delete = {exp[2] for exp in experiments_to_check} - files_to_keep

    task = progress.add_task("Deleting old experiment outputs", total=len(files_to_delete))
    for path in files_to_delete:
        if dry_run:
            progress.console.print(f"[dim][To Delete] {path}[/dim]")
        else:
            path.unlink()
        progress.advance(task)
