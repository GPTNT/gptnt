from functools import partial

from gptnt.cli.statics._evaluation import create_and_run_evaluation
from gptnt.cli.statics._fields import (
    AllowThinkingOption,
    DownloadOption,
    LimitInstancesOption,
    PlayerOption,
    ProviderOption,
    ThrowOption,
    UploadOption,
)
from gptnt.specification import PlayerCapabilities
from gptnt.statics.postprocess import convert_normalised_to_absolute, default_postprocess
from gptnt.statics.preprocess import preprocess_grounding_coordinates_instance
from gptnt.statics.prompts import GROUNDING_COORDINATES_PROMPT, format_instruction_with_reasoning
from gptnt.statics.scorers import (
    CoordinateAbsoluteDistanceComparer,
    CoordinateEuclideanDistanceComparer,
    CoordinateInRegionComparer,
    CoordinateValidator,
    Scorer,
    create_scorers,
)


def _build_coordinate_instruction(
    capabilities: PlayerCapabilities, *, allow_thinking: bool
) -> str:
    instruction = GROUNDING_COORDINATES_PROMPT.replace(
        "{IMAGE_WIDTH}", str(capabilities.image_dimensions.width)
    ).replace("{IMAGE_HEIGHT}", str(capabilities.image_dimensions.height))
    return format_instruction_with_reasoning(
        instruction, allow_thinking=allow_thinking, thinking_method=capabilities.thinking_method
    )


def _build_coordinate_scorers(capabilities: PlayerCapabilities) -> list[Scorer]:  # noqa: WPS210
    if capabilities.coordinate_mode == "normalised":
        post_process_func = partial(
            convert_normalised_to_absolute,
            image_width=capabilities.image_dimensions.width,
            image_height=capabilities.image_dimensions.height,
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
            image_height=capabilities.image_dimensions.height,
            image_width=capabilities.image_dimensions.width,
            postprocess_output_func=post_process_func,
        )
    )
    absolute_distance_scorers = create_scorers(
        CoordinateAbsoluteDistanceComparer(
            task_type="grounding",
            image_height=capabilities.image_dimensions.height,
            image_width=capabilities.image_dimensions.width,
            postprocess_output_func=post_process_func,
        )
    )
    for scorer in coordinate_validator_scorers:
        scorer.name = f"{scorer.name}_coordinate_validator"
    for scorer in euclidean_distance_scorers:
        scorer.name = f"{scorer.name}_normalized_euclidean_distance"
    for scorer in absolute_distance_scorers:
        scorer.name = f"{scorer.name}_absolute_distance"

    return [
        *coordinate_validator_scorers,
        *exact_match_scorers,
        *euclidean_distance_scorers,
        *absolute_distance_scorers,
    ]


async def run_defuser_grounding_evaluation(
    *,
    player: PlayerOption,
    provider: ProviderOption = None,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    allow_thinking: AllowThinkingOption = True,
) -> None:
    """Defuser grounding using absolute coordinates."""
    await create_and_run_evaluation(
        player=player,
        provider=provider,
        role="defuser",
        hf_repo_id="GPTNT/defuser-grounding-dataset",
        dataset_split="test_coordinates",
        task_name="defuser-grounding-coordinates",
        weave_project="gptnt/defuser-grounding-coordinates",
        preprocess_instance_func=preprocess_grounding_coordinates_instance,
        build_instruction=partial(_build_coordinate_instruction, allow_thinking=allow_thinking),
        build_scorers=_build_coordinate_scorers,
        should_download=should_download,
        should_throw=should_throw,
        should_upload=should_upload,
        limit_instances=limit_instances,
    )
