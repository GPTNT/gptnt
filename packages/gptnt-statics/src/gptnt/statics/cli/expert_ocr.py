from functools import partial

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
from gptnt.statics.evaluation.postprocess import expert_ocr_postprocess
from gptnt.statics.evaluation.preprocess import preprocess_expert_ocr_instance
from gptnt.statics.evaluation.prompts import OCR_INSTRUCTION, format_instruction_with_reasoning
from gptnt.statics.evaluation.scorers import StringBasedComparer, create_scorers


async def run_expert_ocr_evaluation(
    *,
    model: ModelOption,
    provider: ProviderOption = None,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    allow_thinking: AllowThinkingOption = True,
) -> None:
    """Expert OCR evaluation."""
    await create_and_run_evaluation(
        model=model,
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
    )


async def run_expert_ocr_with_text_evaluation(
    *,
    model: ModelOption,
    provider: ProviderOption = None,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    allow_thinking: AllowThinkingOption = True,
) -> None:
    """Expert OCR evaluation with the image AND the text."""
    await create_and_run_evaluation(
        model=model,
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
    )
