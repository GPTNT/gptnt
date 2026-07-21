from functools import partial

from gptnt.cli._params import PlayerOption, ProviderOption
from gptnt.cli.statics._evaluation import create_and_run_evaluation
from gptnt.cli.statics._params import (
    AllowThinkingOption,
    DatasetRevisionOption,
    DownloadOption,
    LimitInstancesOption,
    ThrowOption,
    UploadOption,
)
from gptnt.statics.preprocess import preprocess_expert_vqa_instance
from gptnt.statics.prompts import MCQ_INSTRUCTION, format_instruction_with_reasoning
from gptnt.statics.scorers import StringBasedComparer, create_scorers


async def run_expert_vqa_evaluation(
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
    """Expert VQA evaluation."""
    await create_and_run_evaluation(
        player=player,
        provider=provider,
        role="expert",
        hf_repo_id="GPTNT/expert-VQA",
        task_name="expert-vqa",
        weave_project="gptnt/expert-vqa",
        preprocess_instance_func=preprocess_expert_vqa_instance,
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
        dataset_revision=dataset_revision,
    )


async def run_expert_vqa_no_manual_evaluation(
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
    """Expert VQA evaluation."""
    await create_and_run_evaluation(
        player=player,
        provider=provider,
        role="expert",
        hf_repo_id="GPTNT/expert-VQA",
        task_name="expert-vqa-no-manual",
        weave_project="gptnt/expert-vqa-no-manual",
        preprocess_instance_func=partial(preprocess_expert_vqa_instance, include_manual=False),
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
        dataset_revision=dataset_revision,
    )
