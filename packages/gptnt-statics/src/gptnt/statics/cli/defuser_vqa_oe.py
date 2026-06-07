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


async def run_defuser_oe_vqa_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    allow_thinking: AllowThinkingOption = True,
) -> None:
    """Defuser VQA open-ended questions."""
    from gptnt.statics.cli._config_loader import ConfigLoader
    from gptnt.statics.evaluation.preprocess import preprocess_defuser_vqa_open_ended_instance
    from gptnt.statics.evaluation.prompts import (
        OPEN_ENDED_INSTRUCTION,
        format_instruction_with_reasoning,
    )
    from gptnt.statics.evaluation.run import RunHFDatasetEvaluation
    from gptnt.statics.evaluation.scorers import StringBasedComparer, create_scorers

    config_loader = ConfigLoader(player_spec=model, role="defuser")
    instruction = format_instruction_with_reasoning(
        OPEN_ENDED_INSTRUCTION,
        allow_thinking=allow_thinking,
        thinking_method=config_loader.capabilities.thinking_method,
    )
    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/defuser-vqa-oe-dataset",
        dataset_split="test",
        task_name="defuser-vqa-oe",
        weave_project="gptnt/defuser-vqa-open_ended",
        preprocess_instance_func=preprocess_defuser_vqa_open_ended_instance,
        agent=config_loader.agent_fn(instructions=instruction),
        capabilities=config_loader.capabilities,
        scorers=create_scorers(StringBasedComparer(task_type="oe")),
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
