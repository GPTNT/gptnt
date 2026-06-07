from typing import Annotated

import typer
from structlog import get_logger

from gptnt.core.common.paths import Paths

logger = get_logger()
paths = Paths()


def generate_experiment_specs(
    overrides: Annotated[
        list[str] | None,
        typer.Argument(help="Hydra overrides (e.g. experiment=e0-async +seed=42)"),
    ] = None,
) -> None:
    """Generate experiment spec JSON files using Hydra configuration."""
    import hydra
    from rich.progress import track

    from gptnt.core.common.hydra import load_config

    cfg = load_config(config_name="experiment_generator", overrides=overrides)
    instantiated = hydra.utils.instantiate(cfg)

    mission_generator = instantiated["mission_generator"]
    pairing_generator = instantiated["pairing_generator"]
    experiment_generator = instantiated["experiment_generator"]

    missions = mission_generator.generate()
    pairings = pairing_generator.generate()
    experiments = experiment_generator.generate(missions=missions, pairings=pairings)

    paths.experiments.mkdir(parents=True, exist_ok=True)
    for experiment in track(experiments, description="Generating experiments..."):
        file_path = paths.experiments.joinpath(experiment.attempt_name).with_suffix(".json")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        _ = file_path.write_text(experiment.model_dump_json())

    logger.info("Experiments generated successfully.")
