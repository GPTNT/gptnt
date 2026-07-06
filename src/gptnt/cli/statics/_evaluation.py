from collections.abc import Callable

from structlog import get_logger

from gptnt.cli.statics._config_loader import ConfigLoader
from gptnt.players.specification import PlayerCapabilities, PlayerRole
from gptnt.statics.preprocess import PostprocessInputsFunc
from gptnt.statics.run import RunHFDatasetEvaluation
from gptnt.statics.scorers import Scorer

logger = get_logger()


# TODO: Rip the weave out as a primary? we need to make it so that weave uploading is a secondary
#       thing :/


async def create_and_run_evaluation(
    *,
    player: str,
    provider: str | None,
    role: PlayerRole,
    hf_repo_id: str,
    task_name: str,
    weave_project: str,
    preprocess_instance_func: PostprocessInputsFunc,
    build_instruction: Callable[[PlayerCapabilities], str],
    build_scorers: Callable[[PlayerCapabilities], list[Scorer]],
    dataset_split: str | None = None,
    dataset_revision: str | None = None,
    should_download: bool,
    should_throw: bool,
    should_upload: bool,
    limit_instances: int | None,
) -> None:
    """Construct a HuggingFace-dataset evaluation and run the download/throw/upload branches.

    Centralises the setup + branching shared by every statics eval command. Each command supplies
    its task-specific differences (dataset, task name, weave project, instruction, scorers) via
    arguments and the two builder callbacks, which receive the loaded `PlayerCapabilities` so
    capability-dependent instructions/scorers can be derived.

    Args:
        player: Player config name selecting the player.
        provider: Optional provider config override.
        role: Player role (`defuser`/`expert`) used to resize observation images.
        hf_repo_id: HuggingFace dataset repo identifier.
        task_name: Task name used for output directories and metrics.
        weave_project: Weave project to publish results to on upload.
        preprocess_instance_func: Per-instance preprocessing function.
        build_instruction: Callback building the system instruction from capabilities.
        build_scorers: Callback building the scorer list from capabilities.
        dataset_split: Optional HuggingFace dataset split to load.
        dataset_revision: Optional dataset revision (branch, tag, or commit sha) to pin.
        should_download: Whether to download the dataset up-front before running.
        should_throw: Whether to actually execute the evaluation.
        should_upload: Whether to upload the evaluation results to Weave.
        limit_instances: Optional cap on the number of instances to evaluate.
    """
    config_loader = ConfigLoader(player=player, provider=provider, role=role)
    capabilities = config_loader.capabilities
    runner = RunHFDatasetEvaluation(
        hf_repo_id=hf_repo_id,
        dataset_split=dataset_split,
        revision=dataset_revision,
        task_name=task_name,
        weave_project=weave_project,
        preprocess_instance_func=preprocess_instance_func,
        agent=config_loader.agent_fn(instructions=build_instruction(capabilities)),
        capabilities=capabilities,
        scorers=build_scorers(capabilities),
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
