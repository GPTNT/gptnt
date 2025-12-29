from collections.abc import Callable
from typing import Annotated

import hydra
import typer
from pydantic_ai import Agent
from structlog import get_logger

from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths
from gptnt.evaluation.preprocess import (
    preprocess_defuser_vqa_mcq_instance,
    preprocess_defuser_vqa_open_ended_instance,
    preprocess_expert_grounding_instance,
    preprocess_expert_ocr_instance,
    preprocess_expert_vqa_instance,
    preprocess_grounding_instance,
)
from gptnt.evaluation.run import (
    DEFAULT_INSTRUCTION,
    MCQ_INSTRUCTION,
    OCR_INSTRUCTION,
    RunHFDatasetEvaluation,
)

configure_logging()
logger = get_logger()
paths = Paths()


app = typer.Typer()

ModelOption = Annotated[str, typer.Option(help="The model to use.")]
DownloadOption = Annotated[
    bool, typer.Option("--download", help="Download the dataset up-front (mainly for debugging)")
]
ThrowOption = Annotated[bool, typer.Option("--throw", help="Should we throw the evaluation?")]
UploadOption = Annotated[
    bool, typer.Option("--upload", help="Should we upload the evaluation results?")
]


def load_agent(model: str) -> Callable[..., Agent]:
    """Load the agent from the Hydra config with the given model."""
    with hydra.initialize_config_dir(version_base="1.3", config_dir=str(paths.configs)):
        config = hydra.compose(config_name="player", overrides=[f"model={model}"])
    # Instantiate a partial func for creating the agent from the class
    agent = hydra.utils.instantiate(config.player.action_predictor.agent, _partial_=True)
    return agent


@app.command("defuser-grounding")
def run_defuser_grounding_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
) -> None:
    """Run the defuser grounding evaluation."""
    agent_fn = load_agent(model)
    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/defuser-grounding-dataset",
        dataset_split="test",
        task_name="defuser-grounding",
        task_type="grounding",
        weave_project="gptnt/defuser-grounding",
        preprocess_instance_func=preprocess_grounding_instance,
        agent=agent_fn(instructions=DEFAULT_INSTRUCTION),
    )
    if should_download:
        logger.info("Downloading dataset before running evaluation")
        _ = runner.load_dataset()

    logger.info("Running evaluation", agent=runner.agent)
    if should_throw:
        runner.throw()
    if should_upload:
        runner.upload()
    logger.info("Evaluation completed successfully", agent=runner.agent)


@app.command("defuser-vqa-oe")
def run_defuser_oe_vqa_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
) -> None:
    """Run the defuser VQA."""
    agent_fn = load_agent(model)
    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/defuser-vqa-oe-dataset",
        dataset_split="test",
        task_name="defuser-vqa-oe",
        task_type="vqa",
        weave_project="gptnt/defuser-vqa-open_ended",
        preprocess_instance_func=preprocess_defuser_vqa_open_ended_instance,
        agent=agent_fn(instructions=DEFAULT_INSTRUCTION),
    )
    if should_download:
        logger.info("Downloading dataset before running evaluation")
        _ = runner.load_dataset()

    logger.info("Running defuser VQA evaluation", agent=runner.agent)
    if should_throw:
        runner.throw()
    if should_upload:
        runner.upload()
    logger.info("Defuser OE VQA evaluation completed successfully", agent=runner.agent)


@app.command("defuser-vqa-mcq")
def run_defuser_mcq_vqa_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
) -> None:
    """Run the defuser VQA evaluation on multiple choice questions."""
    agent_fn = load_agent(model)
    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/defuser-vqa-mc-dataset",
        dataset_split="test",
        task_name="defuser-vqa-mcq",
        task_type="vqa",
        weave_project="gptnt/defuser-vqa-mcq",
        preprocess_instance_func=preprocess_defuser_vqa_mcq_instance,
        agent=agent_fn(instructions=MCQ_INSTRUCTION),
    )
    if should_download:
        logger.info("Downloading dataset before running evaluation")
        _ = runner.load_dataset()

    logger.info("Running defuser MCQ VQA evaluation", agent=runner.agent)
    if should_throw:
        runner.throw()
    if should_upload:
        runner.upload()
    logger.info("Defuser MCQ VQA evaluation completed successfully", agent=runner.agent)


@app.command("expert-vqa")
def run_expert_vqa_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
) -> None:
    """Run the expert VQA evaluation."""
    agent_fn = load_agent(model)
    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/expert-VQA",
        task_name="expert-vqa",
        task_type="expert_vqa",
        weave_project="gptnt/expert-vqa",
        preprocess_instance_func=preprocess_expert_vqa_instance,
        agent=agent_fn(instructions=MCQ_INSTRUCTION),
    )
    if should_download:
        logger.info("Downloading dataset before running evaluation")
        _ = runner.load_dataset()

    logger.info("Running expert VQA evaluation", agent=runner.agent)
    if should_throw:
        runner.throw()
    if should_upload:
        runner.upload()
    logger.info("Expert VQA evaluation completed successfully", agent=runner.agent)


@app.command("expert-ocr")
def run_expert_ocr_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
) -> None:
    """Run the expert OCR evaluation."""
    agent_fn = load_agent(model)
    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/expert-element-ocr",
        task_name="expert-ocr",
        task_type="expert_vqa",
        weave_project="gptnt/expert-ocr",
        preprocess_instance_func=preprocess_expert_ocr_instance,
        agent=agent_fn(instructions=OCR_INSTRUCTION),
    )
    if should_download:
        logger.info("Downloading dataset before running evaluation")
        _ = runner.load_dataset()

    logger.info("Running expert OCR evaluation", agent=runner.agent)
    if should_throw:
        runner.throw()
    if should_upload:
        runner.upload()
    logger.info("Expert OCR evaluation completed successfully", agent=runner.agent)


@app.command("expert-element-grounding")
def run_expert_grounding_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
) -> None:
    """Run the expert grounding evaluation."""
    agent_fn = load_agent(model)
    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/expert-element-grounding",
        task_name="expert-element-grounding",
        task_type="expert_vqa",
        weave_project="gptnt/expert-element-grounding",
        preprocess_instance_func=preprocess_expert_grounding_instance,
        agent=agent_fn(instructions=MCQ_INSTRUCTION),
    )
    if should_download:
        logger.info("Downloading dataset before running evaluation")
        _ = runner.load_dataset()

    logger.info("Running expert grounding evaluation", agent=runner.agent)
    if should_throw:
        runner.throw()
    if should_upload:
        runner.upload()
    logger.info("Expert grounding evaluation completed successfully", agent=runner.agent)


if __name__ == "__main__":
    app()
