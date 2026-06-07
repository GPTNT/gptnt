from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings
from whenever import Instant


def remove_empty_experiment_recorder_outputs(root_path: Path) -> None:
    """Remove empty experiment recorder output directories."""
    for path in root_path.glob("*"):
        if path.exists() and path.is_dir() and not any(path.iterdir()):
            path.rmdir()


class Paths(BaseSettings):
    """Paths and locations for things."""

    root: Path = Path.cwd()

    configs: Path = root.joinpath("configs")
    storage: Path = root.joinpath("storage")
    artifacts: Path = root.joinpath("artifacts")

    generated: Path = root.joinpath("output")
    output: Path = generated.joinpath("outputs")
    logs: Path = generated.joinpath("logs")

    output_observations: Path = output.joinpath("observations")
    experiment_recorder: Path = output.joinpath("experiment_recorder_outputs")
    experiment_recorder_outputs: Path | None = Field(
        default=None, alias="EXPERIMENT_RECORDER_OUTPUTS"
    )
    experiments_db: Path = output.joinpath("experiments.duckdb")

    experiments: Path = generated.joinpath("experiments")
    test_experiments: Path = storage.joinpath("test_experiments")
    vqa_and_grounding: Path = storage.joinpath("statics-data")
    expert_vqa: Path = storage.joinpath("expert_vqa")

    ktane: Path = storage.joinpath("ktane")
    """Path to the where we store the game."""

    prompts: Path = storage.joinpath("prompts")
    """Path to the where we store the prompts pieces."""

    @property
    def experiment_outputs(self) -> Path:
        """Get path for experiment recorder outputs with a timestamp."""
        if self.experiment_recorder_outputs is not None:
            return self.experiment_recorder_outputs

        timestamp = Instant.now().format_iso().replace("/", "-").replace(":", "-")
        path = self.experiment_recorder.joinpath(f"{timestamp}/")
        return path

    @property
    def span_timings_dir(self) -> Path:
        """Directory for per-process span-timing JSONL files (benchmark overhead capture).

        Sits alongside the experiment JSON records for the same run so the two can be joined
        on `session_id` at analysis time.
        """
        return self.experiment_outputs.joinpath("span_timings")
