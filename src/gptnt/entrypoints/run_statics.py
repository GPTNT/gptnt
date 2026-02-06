from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Annotated

import hydra
import typer
from omegaconf import DictConfig
from pydantic_ai import Agent
from structlog import get_logger

from gptnt.common.async_typer import AsyncTyper
from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths
from gptnt.evaluation.postprocess import (
    convert_normalised_to_absolute,
    default_postprocess,
    expert_ocr_postprocess,
)
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
    REASONING_PROMPT,
    RunHFDatasetEvaluation,
)
from gptnt.evaluation.scorers import (
    CoordinateAbsoluteDistanceComparer,
    CoordinateEuclideanDistanceComparer,
    CoordinateInRegionComparer,
    CoordinateValidator,
    StringBasedComparer,
    create_scorers,
)
from gptnt.players.specification import PlayerCapabilities, PlayerRole
from gptnt.processors.image_resizer import ImageResizer

configure_logging()
logger = get_logger()
paths = Paths()


app = AsyncTyper()

ModelOption = Annotated[str, typer.Option(help="The model to use.")]
DownloadOption = Annotated[
    bool, typer.Option("--download", help="Download the dataset up-front (mainly for debugging)")
]
ThrowOption = Annotated[bool, typer.Option("--throw", help="Should we throw the evaluation?")]
UploadOption = Annotated[
    bool, typer.Option("--upload", help="Should we upload the evaluation results?")
]
LimitInstancesOption = Annotated[
    int | None,
    typer.Option(
        "--limit-instances", help="Limit the number of instances to evaluate on (for debugging)"
    ),
]


def format_instruction_with_reasoning(
    instruction: str, *, allow_thinking: bool, thinking_method: str
) -> str:
    """Prepends the appropriate reasoning prompt to the instruction."""
    if allow_thinking:
        reasoning_prompt = REASONING_PROMPT

        if thinking_method == "inner-monologue":
            reasoning_prompt = REASONING_PROMPT.replace("thought", "think").replace(
                "reasoning", "thinking_process"
            )

        return f"{reasoning_prompt} {instruction}"

    return instruction


@dataclass(kw_only=True)
class ConfigLoader:
    """Easily parse and load things from the config."""

    model: str
    role: PlayerRole

    @property
    def config(self) -> DictConfig:
        """Load the config."""
        with hydra.initialize_config_dir(version_base="1.3", config_dir=str(paths.configs)):
            config = hydra.compose(config_name="player", overrides=[f"model={self.model}"])
        return config

    @property
    def image_resizer(self) -> ImageResizer:
        """Instantiate the image resizer from the config."""
        capabilities = self.capabilities
        match self.role:
            case "defuser":
                target_width = capabilities.image_dimensions.long_side
                target_height = capabilities.image_dimensions.short_side
            case "expert":
                target_width = capabilities.image_dimensions.short_side
                target_height = capabilities.image_dimensions.long_side
        image_resizer = hydra.utils.instantiate(
            self.config.player.observation_handler.image_resizer,
            target_width=target_width,
            target_height=target_height,
        )
        return image_resizer

    @property
    def capabilities(self) -> PlayerCapabilities:
        """Grab the reasoning parser from the Capabilities."""
        capabilities = hydra.utils.instantiate(self.config.player.capabilities)
        return capabilities

    @property
    def agent_fn(self) -> Callable[..., Agent]:
        """Instantiate a partial func for creating the agent from the class."""
        agent = hydra.utils.instantiate(self.config.player.action_predictor.agent, _partial_=True)
        return agent


@app.command("defuser-grounding-coordinates")
async def run_defuser_grounding_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    allow_thinking: bool = True,
) -> None:
    """Run the defuser grounding evaluation."""
    config_loader = ConfigLoader(model=model, role="defuser")
    instruction = GROUNDING_COORDINATES_PROMPT.replace(
        "{IMAGE_WIDTH}", str(config_loader.capabilities.image_dimensions.width)
    ).replace("{IMAGE_HEIGHT}", str(config_loader.capabilities.image_dimensions.height))

    instruction = format_instruction_with_reasoning(
        instruction,
        allow_thinking=allow_thinking,
        thinking_method=config_loader.capabilities.thinking_method,
    )

    if config_loader.capabilities.coordinate_mode == "normalised":
        post_process_func = partial(
            convert_normalised_to_absolute,
            image_width=config_loader.capabilities.image_dimensions.width,
            image_height=config_loader.capabilities.image_dimensions.height,
        )
    else:
        post_process_func = default_postprocess

    # Create the weave scorers
    coordinate_validator_scorers = create_scorers(
        CoordinateValidator(task_type="grounding", postprocess_output_func=post_process_func)
    )
    exact_match_scorers = create_scorers(
        CoordinateInRegionComparer(
            task_type="grounding", postprocess_output_func=post_process_func
        )
    )
    euclidean_distance_scorers = create_scorers(
        CoordinateEuclideanDistanceComparer(
            task_type="grounding",
            image_height=config_loader.capabilities.image_dimensions.height,
            image_width=config_loader.capabilities.image_dimensions.width,
            postprocess_output_func=post_process_func,
        )
    )
    absolute_distance_scorers = create_scorers(
        CoordinateAbsoluteDistanceComparer(
            task_type="grounding",
            image_height=config_loader.capabilities.image_dimensions.height,
            image_width=config_loader.capabilities.image_dimensions.width,
            postprocess_output_func=post_process_func,
        )
    )
    # Update the names for the distance scorers to prevent name clashes in weave
    for scorer in coordinate_validator_scorers:
        scorer.name = f"{scorer.name}_coordinate_validator"
    for scorer in euclidean_distance_scorers:
        scorer.name = f"{scorer.name}_normalized_euclidean_distance"
    for scorer in absolute_distance_scorers:
        scorer.name = f"{scorer.name}_absolute_distance"

    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/defuser-grounding-dataset",
        dataset_split="test_coordinates",
        task_name="defuser-grounding-coordinates",
        weave_project="gptnt/defuser-grounding-coordinates",
        preprocess_instance_func=preprocess_grounding_coordinates_instance,
        agent=config_loader.agent_fn(instructions=instruction),
        capabilities=config_loader.capabilities,
        weave_scorers=[
            *coordinate_validator_scorers,
            *exact_match_scorers,
            *euclidean_distance_scorers,
            *absolute_distance_scorers,
        ],
        max_instances=limit_instances,
    )
    if should_download:
        logger.info("Downloading dataset before running evaluation")
        _ = runner.load_dataset()

    logger.info("Running evaluation", agent=runner.agent)
    if should_throw:
        await runner.throw()
    if should_upload:
        await runner.upload()
    logger.info("Evaluation completed successfully", agent=runner.agent)


@app.command("defuser-grounding-som")
async def run_defuser_set_of_marks_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    allow_thinking: bool = True,
) -> None:
    """Run the defuser grounding evaluation."""
    config_loader = ConfigLoader(model=model, role="defuser")
    instruction = format_instruction_with_reasoning(
        GROUNDING_SOM_PROMPT,
        allow_thinking=allow_thinking,
        thinking_method=config_loader.capabilities.thinking_method,
    )

    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/defuser-grounding-dataset",
        dataset_split="test_som",
        task_name="defuser-grounding-som",
        weave_project="gptnt/defuser-grounding-som",
        preprocess_instance_func=preprocess_grounding_set_of_marks_instance,
        agent=config_loader.agent_fn(instructions=instruction),
        capabilities=config_loader.capabilities,
        weave_scorers=create_scorers(StringBasedComparer(task_type="grounding")),
        max_instances=limit_instances,
    )
    if should_download:
        logger.info("Downloading dataset before running evaluation")
        _ = runner.load_dataset()

    logger.info("Running evaluation", agent=runner.agent)
    if should_throw:
        await runner.throw()
    if should_upload:
        await runner.upload()
    logger.info("Evaluation completed successfully", agent=runner.agent)


@app.command("defuser-vqa-oe")
async def run_defuser_oe_vqa_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    allow_thinking: bool = True,
) -> None:
    """Run the defuser VQA."""
    config_loader = ConfigLoader(model=model, role="defuser")
    instruction = format_instruction_with_reasoning(
        OPEN_ENDED_INSTRUCTION,
        allow_thinking=allow_thinking,
        thinking_method=config_loader.capabilities.thinking_method,
    )

    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/defuser-vqa-oe-dataset",
        dataset_split="test",
        task_name="defuser-vqa-oe",
        weave_project="gptnt/defuser-vqa-open_ended",
        preprocess_instance_func=preprocess_defuser_vqa_open_ended_instance,
        agent=config_loader.agent_fn(instructions=instruction),
        capabilities=config_loader.capabilities,
        weave_scorers=create_scorers(StringBasedComparer(task_type="vqa")),
        max_instances=limit_instances,
    )
    if should_download:
        logger.info("Downloading dataset before running evaluation")
        _ = runner.load_dataset()

    logger.info("Running defuser VQA evaluation", agent=runner.agent)
    if should_throw:
        await runner.throw()
    if should_upload:
        await runner.upload()
    logger.info("Defuser OE VQA evaluation completed successfully", agent=runner.agent)


@app.command("defuser-vqa-mcq")
async def run_defuser_mcq_vqa_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    allow_thinking: bool = True,
) -> None:
    """Run the defuser VQA evaluation on multiple choice questions."""
    config_loader = ConfigLoader(model=model, role="defuser")
    instruction = format_instruction_with_reasoning(
        MCQ_INSTRUCTION,
        allow_thinking=allow_thinking,
        thinking_method=config_loader.capabilities.thinking_method,
    )

    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/defuser-vqa-mc-dataset",
        dataset_split="test",
        task_name="defuser-vqa-mcq",
        weave_project="gptnt/defuser-vqa-mcq",
        preprocess_instance_func=preprocess_defuser_vqa_mcq_instance,
        agent=config_loader.agent_fn(instructions=instruction),
        capabilities=config_loader.capabilities,
        weave_scorers=create_scorers(StringBasedComparer(task_type="vqa")),
        max_instances=limit_instances,
    )
    if should_download:
        logger.info("Downloading dataset before running evaluation")
        _ = runner.load_dataset()

    logger.info("Running defuser MCQ VQA evaluation", agent=runner.agent)
    if should_throw:
        await runner.throw()
    if should_upload:
        await runner.upload()
    logger.info("Defuser MCQ VQA evaluation completed successfully", agent=runner.agent)


@app.command("expert-vqa")
async def run_expert_vqa_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    allow_thinking: bool = True,
) -> None:
    """Run the expert VQA evaluation."""
    config_loader = ConfigLoader(model=model, role="expert")
    instruction = format_instruction_with_reasoning(
        MCQ_INSTRUCTION,
        allow_thinking=allow_thinking,
        thinking_method=config_loader.capabilities.thinking_method,
    )

    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/expert-VQA",
        task_name="expert-vqa",
        weave_project="gptnt/expert-vqa",
        preprocess_instance_func=preprocess_expert_vqa_instance,
        agent=config_loader.agent_fn(instructions=instruction),
        capabilities=config_loader.capabilities,
        weave_scorers=create_scorers(StringBasedComparer(task_type=None)),
        max_instances=limit_instances,
    )
    if should_download:
        logger.info("Downloading dataset before running evaluation")
        _ = runner.load_dataset()

    logger.info("Running expert VQA evaluation", agent=runner.agent)
    if should_throw:
        await runner.throw()
    if should_upload:
        await runner.upload()
    logger.info("Expert VQA evaluation completed successfully", agent=runner.agent)


@app.command("expert-ocr")
async def run_expert_ocr_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    allow_thinking: bool = True,
) -> None:
    """Run the expert OCR evaluation."""
    config_loader = ConfigLoader(model=model, role="expert")
    instruction = format_instruction_with_reasoning(
        OCR_INSTRUCTION,
        allow_thinking=allow_thinking,
        thinking_method=config_loader.capabilities.thinking_method,
    )

    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/expert-element-ocr",
        task_name="expert-ocr",
        weave_project="gptnt/expert-ocr",
        preprocess_instance_func=preprocess_expert_ocr_instance,
        agent=config_loader.agent_fn(instructions=instruction),
        capabilities=config_loader.capabilities,
        weave_scorers=create_scorers(
            StringBasedComparer(task_type=None, postprocess_output_func=expert_ocr_postprocess)
        ),
        max_instances=limit_instances,
    )
    if should_download:
        logger.info("Downloading dataset before running evaluation")
        _ = runner.load_dataset()

    logger.info("Running expert OCR evaluation", agent=runner.agent)
    if should_throw:
        await runner.throw()
    if should_upload:
        await runner.upload()
    logger.info("Expert OCR evaluation completed successfully", agent=runner.agent)


@app.command("expert-element-grounding")
async def run_expert_grounding_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    allow_thinking: bool = True,
) -> None:
    """Run the expert grounding evaluation."""
    config_loader = ConfigLoader(model=model, role="expert")
    instruction = format_instruction_with_reasoning(
        MCQ_INSTRUCTION,
        allow_thinking=allow_thinking,
        thinking_method=config_loader.capabilities.thinking_method,
    )

    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/expert-element-grounding",
        task_name="expert-element-grounding",
        preprocess_instance_func=preprocess_expert_grounding_instance,
        agent=config_loader.agent_fn(instructions=instruction),
        capabilities=config_loader.capabilities,
        weave_project="gptnt/expert-element-grounding",
        weave_scorers=create_scorers(StringBasedComparer(task_type=None)),
        max_instances=limit_instances,
    )
    if should_download:
        logger.info("Downloading dataset before running evaluation")
        _ = runner.load_dataset()

    logger.info("Running expert grounding evaluation", agent=runner.agent)
    if should_throw:
        await runner.throw()
    if should_upload:
        await runner.upload()
    logger.info("Expert grounding evaluation completed successfully", agent=runner.agent)


if __name__ == "__main__":
    app()
