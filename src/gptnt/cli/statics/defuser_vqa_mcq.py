from gptnt.cli.statics._evaluation import create_and_run_evaluation
from gptnt.cli.statics._fields import (
    AllowThinkingOption,
    DatasetRevisionOption,
    DownloadOption,
    LimitInstancesOption,
    PlayerOption,
    ProviderOption,
    StateRecognitionSplitOption,
    ThrowOption,
    UploadOption,
)
from gptnt.statics.preprocess import preprocess_defuser_vqa_mcq_instance
from gptnt.statics.prompts import MCQ_INSTRUCTION, format_instruction_with_reasoning
from gptnt.statics.scorers import StringBasedComparer, create_scorers

STATE_RECOGNITION_SPLITS = {
    "state-change": "test_state_change",
    "solved": "test_solved",
    "strikes": "test_strikes",
}


async def run_defuser_mcq_vqa_evaluation(
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
    """Defuser VQA multiple choice questions."""
    await create_and_run_evaluation(
        player=player,
        provider=provider,
        role="defuser",
        hf_repo_id="GPTNT/defuser-vqa-mc-dataset",
        dataset_split="test",
        task_name="defuser-vqa-mcq",
        weave_project="gptnt/defuser-vqa-mcq",
        preprocess_instance_func=preprocess_defuser_vqa_mcq_instance,
        build_instruction=lambda capabilities: format_instruction_with_reasoning(
            MCQ_INSTRUCTION,
            allow_thinking=allow_thinking,
            thinking_method=capabilities.thinking_method,
        ),
        build_scorers=lambda _capabilities: create_scorers(StringBasedComparer(task_type="vqa")),
        should_download=should_download,
        should_throw=should_throw,
        should_upload=should_upload,
        limit_instances=limit_instances,
        dataset_revision=dataset_revision,
    )


async def run_defuser_state_recognition_vqa_evaluation(
    *,
    player: PlayerOption,
    provider: ProviderOption = None,
    state_split: StateRecognitionSplitOption = "state-change",
    should_download: DownloadOption = False,
    should_throw: ThrowOption = False,
    should_upload: UploadOption = False,
    limit_instances: LimitInstancesOption = None,
    dataset_revision: DatasetRevisionOption = None,
    allow_thinking: AllowThinkingOption = True,
) -> None:
    """Defuser VQA multiple-choice state-recognition questions."""
    if state_split not in STATE_RECOGNITION_SPLITS:
        expected = ", ".join(STATE_RECOGNITION_SPLITS)
        raise ValueError(
            f"Unknown state-recognition split: {state_split}. Expected one of: {expected}."
        )

    await create_and_run_evaluation(
        player=player,
        provider=provider,
        role="defuser",
        hf_repo_id="GPTNT/defuser-state-recognition-vqa-mc-dataset",
        dataset_split=STATE_RECOGNITION_SPLITS[state_split],
        task_name=f"defuser-vqa-mcq-state-{state_split}",
        weave_project=f"gptnt/defuser-vqa-mcq-state-{state_split}",
        preprocess_instance_func=preprocess_defuser_vqa_mcq_instance,
        build_instruction=lambda capabilities: format_instruction_with_reasoning(
            MCQ_INSTRUCTION,
            allow_thinking=allow_thinking,
            thinking_method=capabilities.thinking_method,
        ),
        build_scorers=lambda _capabilities: create_scorers(StringBasedComparer(task_type="vqa")),
        should_download=should_download,
        should_throw=should_throw,
        should_upload=should_upload,
        limit_instances=limit_instances,
        dataset_revision=dataset_revision,
    )
