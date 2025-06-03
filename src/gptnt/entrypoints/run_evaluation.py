from typing import Annotated

import hydra
import typer
from pydantic_ai import Agent
from structlog import get_logger

from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths
from gptnt.dataset.evaluation_logger import send_to_weave, throw_weave_eval

configure_logging()
logger = get_logger()
paths = Paths()


app = typer.Typer()


ModelOption = Annotated[str, typer.Option(help="The model to use.")]
ThrowOption = Annotated[bool, typer.Option("--throw", help="Should we throw the evaluation?")]
UploadOption = Annotated[
    bool, typer.Option("--upload", help="Should we upload the evaluation results?")
]


def load_agent(model: str) -> Agent:
    """Load the agent from the Hydra config with the given model."""
    with hydra.initialize_config_dir(version_base="1.3", config_dir=str(paths.configs)):
        config = hydra.compose(config_name="player", overrides=[f"model={model}"])
    # Instantiate the agent from the class
    agent: Agent = hydra.utils.instantiate(config.player.agent)
    assert isinstance(agent, Agent), "The instantiated agent is not an Agent."
    return agent


@app.command("grounding")
def run_grounding_evaluation(
    *, model: ModelOption, should_throw: ThrowOption = False, should_upload: UploadOption = False
) -> None:
    """Run the defuser grounding evaluation."""
    agent = load_agent(model)
    logger.info("Running evaluation", agent=agent)

    if should_throw:
        throw_weave_eval(name="grounding", agent=agent, hf_dataset="GPTNT/grounding-dataset")
    if should_upload:
        send_to_weave(name="grounding", agent=agent, hf_dataset="GPTNT/grounding-dataset")

    logger.info("Evaluation completed successfully", agent=agent)


@app.command("vqa")
def run_vqa_evaluation(
    *, model: ModelOption, should_throw: ThrowOption = False, should_upload: UploadOption = False
) -> None:
    """Run the defuser VQA."""
    agent = load_agent(model)
    logger.info("Running VQA evaluation", agent=agent)
    if should_throw:
        raise NotImplementedError
    if should_upload:
        raise NotImplementedError
    logger.info("VQA evaluation completed successfully", agent=agent)


@app.command("expert-vqa")
def run_expert_vqa_evaluation(
    *, model: ModelOption, should_throw: ThrowOption = False, should_upload: UploadOption = False
) -> None:
    """Run the expert VQA evaluation."""
    agent = load_agent(model)
    logger.info("Running expert VQA evaluation", agent=agent)
    if should_throw:
        raise NotImplementedError
    if should_upload:
        raise NotImplementedError
    logger.info("Expert VQA evaluation completed successfully", agent=agent)


if __name__ == "__main__":
    app()
