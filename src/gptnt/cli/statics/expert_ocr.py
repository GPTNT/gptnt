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
from gptnt.statics.postprocess import expert_ocr_postprocess
from gptnt.statics.preprocess import preprocess_expert_ocr_instance
from gptnt.statics.prompts import OCR_INSTRUCTION, format_instruction_with_reasoning
from gptnt.statics.scorers import StringBasedComparer, create_scorers


async def run_expert_ocr_evaluation(
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
    """Expert OCR evaluation."""
    await create_and_run_evaluation(
        player=player,
        provider=provider,
        role="expert",
        hf_repo_id="GPTNT/expert-element-ocr",
        task_name="expert-ocr",
        weave_project="gptnt/expert-ocr",
        preprocess_instance_func=preprocess_expert_ocr_instance,
        build_instruction=lambda capabilities: format_instruction_with_reasoning(
            OCR_INSTRUCTION,
            allow_thinking=allow_thinking,
            thinking_method=capabilities.thinking_method,
        ),
        build_scorers=lambda _capabilities: create_scorers(
            StringBasedComparer(task_type=None, postprocess_output_func=expert_ocr_postprocess)
        ),
        should_download=should_download,
        should_throw=should_throw,
        should_upload=should_upload,
        limit_instances=limit_instances,
        dataset_revision=dataset_revision,
    )


async def run_expert_ocr_with_text_evaluation(
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
    """Expert OCR evaluation with the image AND the text."""
    await create_and_run_evaluation(
        player=player,
        provider=provider,
        role="expert",
        hf_repo_id="GPTNT/expert-element-ocr",
        task_name="expert-ocr-with-text",
        weave_project="gptnt/expert-ocr-with-text",
        preprocess_instance_func=partial(preprocess_expert_ocr_instance, include_manual_text=True),
        build_instruction=lambda capabilities: format_instruction_with_reasoning(
            OCR_INSTRUCTION,
            allow_thinking=allow_thinking,
            thinking_method=capabilities.thinking_method,
        ),
        build_scorers=lambda _capabilities: create_scorers(
            StringBasedComparer(task_type=None, postprocess_output_func=expert_ocr_postprocess)
        ),
        should_download=should_download,
        should_throw=should_throw,
        should_upload=should_upload,
        limit_instances=limit_instances,
        dataset_revision=dataset_revision,
    )
