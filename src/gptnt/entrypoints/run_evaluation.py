from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

import hydra
import typer
from omegaconf import DictConfig
from pydantic_ai import Agent
from structlog import get_logger

from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths
from gptnt.evaluation.postprocess import expert_ocr_postprocess
from gptnt.evaluation.preprocess import (
    preprocess_defuser_vqa_mcq_instance,
    preprocess_defuser_vqa_open_ended_instance,
    preprocess_expert_grounding_instance,
    preprocess_expert_ocr_instance,
    preprocess_expert_vqa_instance,
    preprocess_grounding_coordinates_instance,
    preprocess_grounding_set_of_marks_instance,
)
from gptnt.evaluation.run import (
    GROUNDING_COORDINATES_PROMPT,
    GROUNDING_SOM_PROMPT,
    MCQ_INSTRUCTION,
    OCR_INSTRUCTION,
    OPEN_ENDED_INSTRUCTION,
    RunHFDatasetEvaluation,
)
from gptnt.evaluation.scorers import (
    CoordinateDistanceComparer,
    CoordinateInRegionComparer,
    StringBasedComparer,
    create_scorers,
)
from gptnt.processors.image_resizer import ImageResizer

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


@dataclass(kw_only=True)
class ConfigLoader:
    """Easily parse and load things from the config."""

    model: str

    @property
    def config(self) -> DictConfig:
        """Load the config."""
        with hydra.initialize_config_dir(version_base="1.3", config_dir=str(paths.configs)):
            config = hydra.compose(config_name="player", overrides=[f"model={self.model}"])
        return config

    @property
    def image_resizer(self) -> ImageResizer:
        """Instantiate the image resizer from the config."""
        image_resizer = hydra.utils.instantiate(self.config.player.preprocessors.image_resizer)
        return image_resizer

    @property
    def agent_fn(self) -> Callable[..., Agent]:
        """Instantiate a partial func for creating the agent from the class."""
        agent = hydra.utils.instantiate(self.config.player.action_predictor.agent, _partial_=True)
        return agent


@app.command("defuser-grounding-coordinates")
def run_defuser_grounding_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
) -> None:
    """Run the defuser grounding evaluation."""
    config_loader = ConfigLoader(model=model)
    instruction = GROUNDING_COORDINATES_PROMPT.replace(
        "{IMAGE_WIDTH}", str(config_loader.image_resizer.target_width)
    ).replace("{IMAGE_HEIGHT}", str(config_loader.image_resizer.target_height))
    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/defuser-grounding-dataset",
        dataset_split="test_coordinates",
        task_name="defuser-grounding",
        weave_project="gptnt/defuser-grounding",
        preprocess_instance_func=preprocess_grounding_coordinates_instance,
        agent=config_loader.agent_fn(instructions=instruction),
        image_resizer=config_loader.image_resizer,
        weave_scorers=[
            *create_scorers(CoordinateInRegionComparer(task_type="grounding")),
            *create_scorers(CoordinateDistanceComparer(task_type="grounding")),
        ],
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


@app.command("defuser-grounding-som")
def run_defuser_set_of_marks_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
) -> None:
    """Run the defuser grounding evaluation."""
    config_loader = ConfigLoader(model=model)
    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/defuser-grounding-dataset",
        dataset_split="test_som",
        task_name="defuser-grounding",
        weave_project="gptnt/defuser-grounding",
        preprocess_instance_func=preprocess_grounding_set_of_marks_instance,
        agent=config_loader.agent_fn(instructions=GROUNDING_SOM_PROMPT),
        image_resizer=config_loader.image_resizer,
        weave_scorers=create_scorers(StringBasedComparer(task_type="grounding")),
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
    config_loader = ConfigLoader(model=model)
    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/defuser-vqa-oe-dataset",
        dataset_split="test",
        task_name="defuser-vqa-oe",
        weave_project="gptnt/defuser-vqa-open_ended",
        preprocess_instance_func=preprocess_defuser_vqa_open_ended_instance,
        agent=config_loader.agent_fn(instructions=OPEN_ENDED_INSTRUCTION),
        image_resizer=config_loader.image_resizer,
        weave_scorers=create_scorers(StringBasedComparer(task_type="vqa")),
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
    config_loader = ConfigLoader(model=model)
    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/defuser-vqa-mc-dataset",
        dataset_split="test",
        task_name="defuser-vqa-mcq",
        weave_project="gptnt/defuser-vqa-mcq",
        preprocess_instance_func=preprocess_defuser_vqa_mcq_instance,
        agent=config_loader.agent_fn(instructions=MCQ_INSTRUCTION),
        image_resizer=config_loader.image_resizer,
        weave_scorers=create_scorers(StringBasedComparer(task_type="vqa")),
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
    config_loader = ConfigLoader(model=model)
    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/expert-VQA",
        task_name="expert-vqa",
        weave_project="gptnt/expert-vqa",
        preprocess_instance_func=preprocess_expert_vqa_instance,
        agent=config_loader.agent_fn(instructions=MCQ_INSTRUCTION),
        image_resizer=config_loader.image_resizer,
        weave_scorers=create_scorers(StringBasedComparer(task_type=None)),
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
    config_loader = ConfigLoader(model=model)
    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/expert-element-ocr",
        task_name="expert-ocr",
        weave_project="gptnt/expert-ocr",
        preprocess_instance_func=preprocess_expert_ocr_instance,
        agent=config_loader.agent_fn(instructions=OCR_INSTRUCTION),
        image_resizer=config_loader.image_resizer,
        weave_scorers=create_scorers(
            StringBasedComparer(task_type=None, postprocess_output_func=expert_ocr_postprocess)
        ),
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
    config_loader = ConfigLoader(model=model)
    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/expert-element-grounding",
        task_name="expert-element-grounding",
        preprocess_instance_func=preprocess_expert_grounding_instance,
        agent=config_loader.agent_fn(instructions=MCQ_INSTRUCTION),
        image_resizer=config_loader.image_resizer,
        weave_project="gptnt/expert-element-grounding",
        weave_scorers=create_scorers(StringBasedComparer(task_type=None)),
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
