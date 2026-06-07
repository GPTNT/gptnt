from datetime import UTC, datetime, timedelta

import structlog
import wandb

from gptnt.records.wandb_runs import get_runs_from_wandb, mark_runs_as_old

WANDB_PATH = "gptnt/dont-stop-believin"
logger = structlog.get_logger()
api = wandb.Api()


def find_runs(
    api: wandb.Api,
    *,
    defuser_name: str | None,
    expert_name: str | None,
    num_errors: int | None,
    cutoff_hours: int | None,
    include_old: bool = False,
):
    filters = {}
    if cutoff_hours is not None:
        cutoff = (datetime.now(tz=UTC) - timedelta(hours=cutoff_hours)).isoformat()
        filters["created_at"] = {"$gte": cutoff}
    if not include_old:
        filters["tags"] = {"$nin": ["old"]}
    if defuser_name is not None and expert_name is not None:
        filters["$or"] = [
            {"config.defuser_name": defuser_name},
            {"config.expert_name": expert_name},
        ]
    elif defuser_name is not None:
        filters["config.defuser_name"] = defuser_name
    elif expert_name is not None:
        filters["config.expert_name"] = expert_name
    if num_errors is not None:
        filters["summary_metrics.total_errors.unknown"] = {"$gte": num_errors}
    return api.runs(WANDB_PATH, filters=filters)


def find_in_output_logs(runs, error_string: str):
    broken_runs = []
    counter = 0
    for run in runs:
        counter += 1
        try:
            logger.info(
                f"Checking run {counter}/{len(runs)}: {run.name} ({run.id}). Runs found so far: {len(found_runs)}"
            )
            log_file = run.files(names=["output.log"])[0]
            content = log_file.download(replace=True).read()
            if error_string in content:
                broken_runs.append(run)
        except (IndexError, Exception):  # noqa: BLE001
            continue
    return broken_runs


def get_related_runs(runs):
    # Extract attempt names from the fetched runs
    attempt_names = {run.config["attempt_name"] for run in runs}

    # Find all wandb runs matching those experiment names
    related_runs = get_runs_from_wandb(
        WANDB_PATH,
        additional_filters=[{"$or": [{"config.attempt_name": name} for name in attempt_names]}],
    )

    # Combine: original runs (by ID) + related runs (by experiment name), deduplicated
    all_run_ids = {run.id for run in runs}
    combined_runs = list(runs)
    for run in related_runs:
        if run.id not in all_run_ids:
            combined_runs.append(run)
            all_run_ids.add(run.id)
    return combined_runs


def get_runs_by_ids(api, run_ids):
    runs = []
    for run_id in run_ids:
        try:
            run = api.run(f"{WANDB_PATH}/{run_id}")
            runs.append(run)
        except Exception:  # noqa: BLE001
            pass
    return runs


runs = find_runs(
    api,
    defuser_name="gemini-3",
    expert_name="gemini-3",
    num_errors=1,
    cutoff_hours=22,
    include_old=False,
)
# runs = get_runs_by_ids(api, ["Example"])
found_runs = find_in_output_logs(runs, "524: A timeout occurred")
combined_runs = get_related_runs(found_runs)

for run in combined_runs:
    logger.info(run.id)


if combined_runs:
    confirm = input("Tag these runs as 'old'? [y/N] ")
    if confirm.strip().lower() == "y":
        mark_runs_as_old(combined_runs)
else:
    logger.info("No broken runs found.")
