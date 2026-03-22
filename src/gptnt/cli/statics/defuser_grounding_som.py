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
from gptnt.evaluation.preprocess import preprocess_grounding_set_of_marks_instance
from gptnt.evaluation.prompts import GROUNDING_SOM_PROMPT, format_instruction_with_reasoning
from gptnt.evaluation.run import RunHFDatasetEvaluation
from gptnt.evaluation.scorers import StringBasedComparer, create_scorers

logger = get_logger()


async def run_defuser_set_of_marks_evaluation(
    *,
    model: ModelOption,
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    allow_thinking: AllowThinkingOption = True,
) -> None:
    """Defuser grounding using Set of Marks."""
    config_loader = ConfigLoader(player_spec=model, role="defuser")
    instruction = format_instruction_with_reasoning(
        GROUNDING_SOM_PROMPT,
        allow_thinking=allow_thinking,
        thinking_method=config_loader.capabilities.thinking_method,
    )
    runner = RunHFDatasetEvaluation(
        hf_repo_id="GPTNT/defuser-grounding-dataset",
        dataset_split="test_som",
        task_name="defuser-grounding-som",
        weave_project="gptnt/defuser-grounding-som",
        preprocess_instance_func=preprocess_grounding_set_of_marks_instance,
        agent=config_loader.agent_fn(instructions=instruction),
        capabilities=config_loader.capabilities,
        weave_scorers=create_scorers(StringBasedComparer(task_type="grounding")),
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
