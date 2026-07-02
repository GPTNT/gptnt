from gptnt.cli.statics._evaluation import create_and_run_evaluation
from gptnt.cli.statics._fields import (
    AllowThinkingOption,
    DatasetRevisionOption,
    DownloadOption,
    LimitInstancesOption,
    PlayerOption,
    ProviderOption,
    ThrowOption,
    UploadOption,
)
from gptnt.statics.preprocess import preprocess_grounding_set_of_marks_instance
from gptnt.statics.prompts import GROUNDING_SOM_PROMPT, format_instruction_with_reasoning
from gptnt.statics.scorers import StringBasedComparer, create_scorers


async def run_defuser_set_of_marks_evaluation(
    *,
    player: PlayerOption,
    provider: ProviderOption = None,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    dataset_revision: DatasetRevisionOption = None,
    allow_thinking: AllowThinkingOption = True,
) -> None:
    """Defuser grounding using Set of Marks."""
    await create_and_run_evaluation(
        player=player,
        provider=provider,
        role="defuser",
        hf_repo_id="GPTNT/defuser-grounding-dataset",
        dataset_split="test_som",
        task_name="defuser-grounding-som",
        weave_project="gptnt/defuser-grounding-som",
        preprocess_instance_func=preprocess_grounding_set_of_marks_instance,
        build_instruction=lambda capabilities: format_instruction_with_reasoning(
            GROUNDING_SOM_PROMPT,
            allow_thinking=allow_thinking,
            thinking_method=capabilities.thinking_method,
        ),
        build_scorers=lambda _capabilities: create_scorers(
            StringBasedComparer(task_type="grounding")
        ),
        should_download=should_download,
        should_throw=should_throw,
        should_upload=should_upload,
        limit_instances=limit_instances,
        dataset_revision=dataset_revision,
    )
