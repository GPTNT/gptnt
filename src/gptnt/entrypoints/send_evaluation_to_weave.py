import sys

import hydra
from pydantic_ai import Agent
from structlog import get_logger

from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths
from gptnt.dataset.evaluation_logger import send_to_weave

configure_logging()
logger = get_logger()
paths = Paths()


def load_agent_from_hydra(*, hydra_overrides: list[str]) -> Agent:
    """Load the agent from the Hydra config."""
    with hydra.initialize_config_dir(version_base="1.3", config_dir=str(paths.configs)):
        config = hydra.compose(config_name="player", overrides=hydra_overrides)
    # Instantiate the agent from the class
    agent: Agent = hydra.utils.instantiate(config.player.agent)
    assert isinstance(agent, Agent), "The instantiated agent is not an Agent."
    return agent


def send_evaluation_to_weave(agent: Agent) -> None:
    """Run the evaluation with the given agent."""
    logger.info("Sending evaluation to weave", agent=agent)
    send_to_weave(name="grounding", agent=agent, hf_dataset="GPTNT/grounding-dataset")


if __name__ == "__main__":
    hydra_overrides = sys.argv[1:] if len(sys.argv) > 1 else []
    if hydra_overrides:
        logger.debug(f"Hydra overrides: {hydra_overrides}")
    agent: Agent[None, str] = load_agent_from_hydra(hydra_overrides=hydra_overrides)
    send_evaluation_to_weave(agent)
