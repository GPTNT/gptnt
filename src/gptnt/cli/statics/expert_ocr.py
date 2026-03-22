from structlog import get_logger

from gptnt.cli.statics._config_loader import ConfigLoader
from gptnt.cli.statics._fields import (
    AllowThinkingOption,
    DownloadOption,
    LimitInstancesOption,
    ModelOption,
    ThrowOption,
    UploadOption,
)
from gptnt.evaluation.postprocess import expert_ocr_postprocess
from gptnt.evaluation.preprocess import preprocess_expert_ocr_instance
from gptnt.evaluation.prompts import OCR_INSTRUCTION, format_instruction_with_reasoning
from gptnt.evaluation.run import RunHFDatasetEvaluation
from gptnt.evaluation.scorers import StringBasedComparer, create_scorers

logger = get_logger()


async def run_expert_ocr_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    allow_thinking: AllowThinkingOption = True,
) -> None:
    """Expert OCR evaluation."""
    config_loader = ConfigLoader(player_spec=model, role="expert")
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
