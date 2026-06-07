from functools import partial

from structlog import get_logger

from gptnt.statics.cli._fields import (
    AllowThinkingOption,
    DownloadOption,
    LimitInstancesOption,
    ModelOption,
    ThrowOption,
    UploadOption,
)

logger = get_logger()


async def run_defuser_grounding_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    allow_thinking: AllowThinkingOption = True,
) -> None:
    """Defuser grounding using absolute coordinates."""
    from gptnt.statics.cli._config_loader import ConfigLoader
    from gptnt.statics.evaluation.postprocess import (
        convert_normalised_to_absolute,
        default_postprocess,
    )
    from gptnt.statics.evaluation.preprocess import preprocess_grounding_coordinates_instance
    from gptnt.statics.evaluation.prompts import (
        GROUNDING_COORDINATES_PROMPT,
        format_instruction_with_reasoning,
    )
    from gptnt.statics.evaluation.run import RunHFDatasetEvaluation
    from gptnt.statics.evaluation.scorers import (
        CoordinateAbsoluteDistanceComparer,
        CoordinateEuclideanDistanceComparer,
        CoordinateInRegionComparer,
        CoordinateValidator,
        create_scorers,
    )

    config_loader = ConfigLoader(player_spec=model, role="defuser")
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
        scorers=[
            *coordinate_validator_scorers,
            *exact_match_scorers,
            *euclidean_distance_scorers,
            *absolute_distance_scorers,
        ],
        max_instances=limit_instances,
        image_resizer=config_loader.image_resizer,
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
