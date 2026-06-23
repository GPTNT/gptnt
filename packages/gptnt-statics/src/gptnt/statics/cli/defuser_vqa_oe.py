from gptnt.statics.cli._evaluation import create_and_run_evaluation
from gptnt.statics.cli._fields import (
    AllowThinkingOption,
    DownloadOption,
    LimitInstancesOption,
    ModelOption,
    ProviderOption,
    ThrowOption,
    UploadOption,
)
from gptnt.statics.evaluation.preprocess import preprocess_defuser_vqa_open_ended_instance
from gptnt.statics.evaluation.prompts import (
    OPEN_ENDED_INSTRUCTION,
    format_instruction_with_reasoning,
)
from gptnt.statics.evaluation.scorers import StringBasedComparer, create_scorers


async def run_defuser_oe_vqa_evaluation(
    *,
    model: ModelOption,
    provider: ProviderOption = None,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    allow_thinking: AllowThinkingOption = True,
) -> None:
    """Defuser VQA open-ended questions."""
    await create_and_run_evaluation(
        model=model,
        provider=provider,
        role="defuser",
        hf_repo_id="GPTNT/defuser-vqa-oe-dataset",
        dataset_split="test",
        task_name="defuser-vqa-oe",
        weave_project="gptnt/defuser-vqa-open_ended",
        preprocess_instance_func=preprocess_defuser_vqa_open_ended_instance,
        build_instruction=lambda capabilities: format_instruction_with_reasoning(
            OPEN_ENDED_INSTRUCTION,
            allow_thinking=allow_thinking,
            thinking_method=capabilities.thinking_method,
        ),
        build_scorers=lambda _capabilities: create_scorers(StringBasedComparer(task_type="oe")),
        should_download=should_download,
        should_throw=should_throw,
        should_upload=should_upload,
        limit_instances=limit_instances,
    )
