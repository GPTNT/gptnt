from typing import Annotated

import hydra
import typer
from pydantic_ai import Agent
from structlog import get_logger

from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths
from gptnt.evaluation.run import (
    RunDefuserVQAMCQEvaluation,
    RunDefuserVQAOpenEndedEvaluation,
    RunExpertVQAEvaluation,
    RunGroundingEvaluation,
)
from gptnt.ktane.manual import KtaneManualPaths
from gptnt.prompts.prompt_cache import PromptCache

configure_logging()
logger = get_logger()
paths = Paths()
ktane_manual_paths = KtaneManualPaths()


app = typer.Typer()


ModelOption = Annotated[str, typer.Option(help="The model to use.")]
ThrowOption = Annotated[bool, typer.Option("--throw", help="Should we throw the evaluation?")]
UploadOption = Annotated[
    bool, typer.Option("--upload", help="Should we upload the evaluation results?")
]


def load_agent(model: str) -> Agent:
    """Load the agent from the Hydra config with the given model."""
    with hydra.initialize_config_dir(version_base="1.3", config_dir=str(paths.configs)):
        config = hydra.compose(
            config_name="player",
            overrides=[
                f"model={model}",
                # Force temperature to be 0 for evaluation
                "player.action_predictor.agent.model_settings.temperature=0.0",
            ],
        )
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
    run_eval = RunGroundingEvaluation(agent=agent)
    if should_throw:
        run_eval.throw()
    if should_upload:
        run_eval.upload()
    logger.info("Evaluation completed successfully", agent=agent)


@app.command("defuser-oe-vqa")
def run_vqa_evaluation(
    *, model: ModelOption, should_throw: ThrowOption = False, should_upload: UploadOption = False
) -> None:
    """Run the defuser VQA."""
    agent = load_agent(model)
    logger.info("Running VQA evaluation", agent=agent)
    run_eval = RunDefuserVQAOpenEndedEvaluation(agent=agent)
    if should_throw:
        run_eval.throw()
    if should_upload:
        run_eval.upload()
    logger.info("Defuser OE VQA evaluation completed successfully", agent=agent)


@app.command("defuser-mcq-vqa")
def run_mcq_vqa_evaluation(
    *, model: ModelOption, should_throw: ThrowOption = False, should_upload: UploadOption = False
) -> None:
    """Run the defuser VQA evaluation on multiple choice questions."""
    agent = load_agent(model)
    logger.info("Running MCQ VQA evaluation", agent=agent)
    run_eval = RunDefuserVQAMCQEvaluation(agent=agent)
    if should_throw:
        run_eval.throw()
    if should_upload:
        run_eval.upload()
    logger.info("Defuser MCQ VQA evaluation completed successfully", agent=agent)


@app.command("expert-vqa")
def run_expert_vqa_evaluation(
    *, model: ModelOption, should_throw: ThrowOption = False, should_upload: UploadOption = False
) -> None:
    """Run the expert VQA evaluation."""
    PromptCache.initialise(
        paths.prompts, ktane_manual_paths.text_dir, ktane_manual_paths.images_small_dir
    )
    agent = load_agent(model)
    logger.info("Running expert VQA evaluation", agent=agent)
    run_eval = RunExpertVQAEvaluation(agent=agent)
    if should_throw:
        run_eval.throw()
    if should_upload:
        run_eval.upload()
    logger.info("Expert VQA evaluation completed successfully", agent=agent)


if __name__ == "__main__":
    app()
