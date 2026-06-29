from gptnt.cli.statics._evaluation import create_and_run_evaluation
from gptnt.cli.statics._fields import (
    AllowThinkingOption,
    DownloadOption,
    LimitInstancesOption,
    ModelOption,
    ProviderOption,
    ThrowOption,
    UploadOption,
)
from gptnt.statics.preprocess import preprocess_expert_grounding_instance
from gptnt.statics.prompts import MCQ_INSTRUCTION, format_instruction_with_reasoning
from gptnt.statics.scorers import StringBasedComparer, create_scorers


async def run_expert_grounding_evaluation(
    *,
    model: ModelOption,
    provider: ProviderOption = None,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    allow_thinking: AllowThinkingOption = True,
) -> None:
    """Expert element grounding evaluation."""
    await create_and_run_evaluation(
        model=model,
        provider=provider,
        role="expert",
        hf_repo_id="GPTNT/expert-element-grounding",
        task_name="expert-element-grounding",
        weave_project="gptnt/expert-element-grounding",
        preprocess_instance_func=preprocess_expert_grounding_instance,
        build_instruction=lambda capabilities: format_instruction_with_reasoning(
            MCQ_INSTRUCTION,
            allow_thinking=allow_thinking,
            thinking_method=capabilities.thinking_method,
        ),
        build_scorers=lambda _capabilities: create_scorers(StringBasedComparer(task_type=None)),
        should_download=should_download,
        should_throw=should_throw,
        should_upload=should_upload,
        limit_instances=limit_instances,
    )
