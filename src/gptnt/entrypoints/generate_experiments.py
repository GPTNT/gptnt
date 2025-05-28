from typing import TYPE_CHECKING

import hydra
from omegaconf import DictConfig
from rich.progress import track
from structlog import get_logger

from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths

if TYPE_CHECKING:
    from gptnt.experiments.experiments import ExperimentGenerator
    from gptnt.experiments.missions import MissionGenerator
    from gptnt.experiments.pairing import PairingGenerator

configure_logging()
logger = get_logger()

paths = Paths()


@hydra.main(config_path=str(paths.configs), config_name="experiment_generator", version_base="1.3")
def generate_experiments(cfg: DictConfig) -> None:  # noqa: WPS210
    """Instantiate an experiment generator from the given configuration."""
    instantiated = hydra.utils.instantiate(cfg)

    mission_generator: MissionGenerator = instantiated["mission_generator"]
    pairing_generator: PairingGenerator = instantiated["pairing_generator"]
    experiment_generator: ExperimentGenerator = instantiated["experiment_generator"]

    missions = mission_generator.generate()
    pairings = pairing_generator.generate()
    experiments = experiment_generator.generate(missions=missions, pairings=pairings)

    paths.experiments.mkdir(parents=True, exist_ok=True)
    for experiment in track(experiments, description="Generating experiments..."):
        file_path = paths.experiments.joinpath(experiment.experiment_name).with_suffix(".json")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        _ = file_path.write_text(experiment.model_dump_json())

    logger.info("Experiments generated successfully.")


if __name__ == "__main__":
    generate_experiments()
