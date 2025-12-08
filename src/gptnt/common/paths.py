from pathlib import Path

from pydantic_settings import BaseSettings
from whenever import Instant


class Paths(BaseSettings):
    """Paths and locations for things."""

    root: Path = Path.cwd()

    configs: Path = root.joinpath("configs")
    storage: Path = root.joinpath("storage")
    artifacts: Path = root.joinpath("artifacts")
    output: Path = storage.joinpath("outputs")

    output_observations: Path = output.joinpath("observations")
    experiment_recorder: Path = output.joinpath("experiment_recorder_outputs")

    experiments: Path = storage.joinpath("experiments")
    test_experiments: Path = storage.joinpath("test_experiments")
    vqa_and_grounding: Path = storage.joinpath("vqa_and_grounding")
    expert_vqa: Path = storage.joinpath("expert_vqa")
    dummy_observation_dataset: Path = storage.joinpath("observation_dataset")
    vqa_and_grounding_hf_dataset: str = "GPTNT/gptnt"
    grounding_hf_dataset: str = "GPTNT/gptnt_grounding"

    logs: Path = storage.joinpath("logs")
    gradio_chats: Path = output.joinpath("gradio_chats")

    ktane: Path = storage.joinpath("ktane")
    """Path to the where we store the game."""

    prompts: Path = storage.joinpath("prompts")
    """Path to the where we store the prompts pieces."""

    @property
    def experiment_recorder_outputs(self) -> Path:
        """Get path for experiment recorder outputs with a timestamp."""
        path = self.experiment_recorder.joinpath(f"{Instant.now().format_common_iso()}/")
        path.mkdir(parents=True, exist_ok=True)
        return path
