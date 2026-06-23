from pathlib import Path
from typing import Annotated

import httpx
from cyclopts import Parameter
from cyclopts.types import ExistingDirectory
from rich.console import Console
from structlog import get_logger

from gptnt.core.common.paths import Paths
from gptnt.core.runtime_settings import RuntimeSettings
from gptnt.experiments.cli.models import SourceOption
from gptnt.experiments.ledger.base import Source
from gptnt.experiments.ledger.resolve import filter_experiments
from gptnt.experiments.spec import ExperimentSpec

logger = get_logger()
paths = Paths()
console = Console()

runtime_settings = RuntimeSettings()


async def send_experiments(experiments: list[ExperimentSpec]) -> None:
    """Send the experiments to the experiment specs queue, confirming the POST landed."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{runtime_settings.em_base_url}/add-specs",
            json={"specs": [experiment.model_dump(mode="json") for experiment in experiments]},
        )
        _ = response.raise_for_status()


async def send_experiment_specs_to_em(
    *,
    experiment_specs_dir: Annotated[
        ExistingDirectory,
        Parameter(help="Path to experiment specs", env_var="EXPERIMENT_SPECS_DIR"),
    ] = paths.experiment_specs,
    source: SourceOption = Source.local,
    output_dir: Annotated[
        Path,
        Parameter(
            help="Where recorded outputs live, for the local completion check.",
            env_var="EXPERIMENT_RECORDER",
        ),
    ] = paths.experiment_recorder_dir,
    dry_run: Annotated[
        bool, Parameter(help="If set, only logs the experiments that would be thrown")
    ] = False,
    no_filter: Annotated[
        bool, Parameter(help="If set, throws every spec without skipping already-done ones")
    ] = False,
    delete_unneeded: Annotated[
        bool, Parameter(help="If set, deletes any unneeded experiment specs from the directory")
    ] = False,
) -> None:
    """Send the experiment specs to the EM queue."""
    if dry_run:
        logger.warning("Dry run mode is enabled. No experiments will be thrown.")

    experiment_paths = list(experiment_specs_dir.rglob("*.json"))
    loaded_experiments = [
        ExperimentSpec.model_validate_json(experiment_path.read_bytes())
        for experiment_path in experiment_paths
    ]

    if not loaded_experiments:
        logger.warning("No experiments found in the directory.")
        return
    logger.info(f"Loaded {len(loaded_experiments)} experiments from '{experiment_specs_dir}'")

    if no_filter:
        logger.warning("Skipping the completion check; throwing every spec.")
    else:
        before = len(loaded_experiments)
        loaded_experiments = filter_experiments(
            loaded_experiments, source=source, output_dir=output_dir
        )
        logger.info(
            f"{len(loaded_experiments)} experiments to throw",
            filtered_out=before - len(loaded_experiments),
            source=source.value,
        )

    if delete_unneeded:
        all_names = [experiment.attempt_name for experiment in loaded_experiments]
        for path in experiment_paths:
            if path.stem not in all_names:
                path.unlink(missing_ok=True)

    if not dry_run:
        await send_experiments(loaded_experiments)
        logger.info("All experiments thrown.")
