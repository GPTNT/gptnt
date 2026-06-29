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

    output: Path = root.joinpath("output")
    logs: Path = output.joinpath("logs")

    output_observations: Path = output.joinpath("observations")
    experiments_db: Path = output.joinpath("experiments.duckdb")

    experiment_specs: Path = Field(
        default=output.joinpath("experiment_specs"), alias="EXPERIMENT_SPECS_DIR"
    )
    """Where generated experiment-spec JSON files live (one subdir per manifest)."""

    experiment_recorder_outputs: Path | None = Field(
        default=None, alias="EXPERIMENT_RECORDER_OUTPUTS"
    )
    """Pin the recorder output dir; unset means a fresh timestamped dir under the recorder base."""

    ktane: Path = storage.joinpath("ktane")
    """Path to the where we store the game."""

    prompts: Path = storage.joinpath("prompts")
    """Path to the where we store the prompts pieces."""

    @property
    def model_configs(self) -> Path:
        """Directory of model configs (`configs/model/`)."""
        return self.configs / "model"

    @property
    def experiment_configs(self) -> Path:
        """Directory of experiment-preset configs (`configs/experiment/`)."""
        return self.configs / "experiment"

    @property
    def experiment_recorder_dir(self) -> Path:
        """The base directory under which each run's timestamped output dir is created."""
        return self.output.joinpath("experiment_recorder_outputs")

    @property
    def experiment_outputs(self) -> Path:
        """The recorder output dir for one run: the pinned dir if set, else a fresh timestamp."""
        if self.experiment_recorder_outputs is not None:
            return self.experiment_recorder_outputs

        timestamp = Instant.now().format_iso().replace("/", "-").replace(":", "-")
        return self.experiment_recorder_dir.joinpath(f"{timestamp}/")

    @property
    def span_timings_dir(self) -> Path:
        """Directory for per-process span-timing JSONL files (benchmark overhead capture).

        Sits alongside the experiment JSON records for the same run so the two can be joined on
        `session_id` at analysis time.
        """
        return self.experiment_outputs.joinpath("span_timings")
