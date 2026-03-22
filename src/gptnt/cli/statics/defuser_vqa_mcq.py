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
from gptnt.evaluation.preprocess import preprocess_defuser_vqa_mcq_instance
from gptnt.evaluation.prompts import MCQ_INSTRUCTION, format_instruction_with_reasoning
from gptnt.evaluation.run import RunHFDatasetEvaluation
from gptnt.evaluation.scorers import StringBasedComparer, create_scorers

logger = get_logger()


async def run_defuser_mcq_vqa_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    allow_thinking: AllowThinkingOption = True,
) -> None:
    """Defuser VQA multiple choice questions."""
    config_loader = ConfigLoader(player_spec=model, role="defuser")
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
