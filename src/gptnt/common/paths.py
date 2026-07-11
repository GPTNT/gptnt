from importlib.resources import files
from pathlib import Path

import structlog
from pydantic import Field
from pydantic_settings import BaseSettings
from whenever import Instant

logger = structlog.get_logger()

SUBMISSION_REPO_SLUG = "gptnt/submissions"
SUBMISSION_REPO_HTTPS = f"https://github.com/{SUBMISSION_REPO_SLUG}"


def remove_empty_experiment_recorder_outputs(root_path: Path) -> None:
    """Remove empty experiment recorder output directories."""
    for path in root_path.glob("*"):
        if path.exists() and path.is_dir() and not any(path.iterdir()):
            path.rmdir()


class Paths(BaseSettings):
    """Paths and locations for things."""

    root: Path = Path.cwd()

    configs_override: Path | None = Field(default=None, alias="CONFIGS")
    """Explicit configs directory; overrides the checkout-then-packaged resolution of `configs`."""

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

    submissions: Path = output.joinpath("submissions")
    """Path to the prepared submissions."""

    @property
    def configs(self) -> Path:
        """Configs directory: the override, the checkout's `configs/`, or the packaged copy.

        A source checkout has `root/configs`. An installed wheel does not, so it falls back to the
        `gptnt/_configs` tree bundled in the wheel.
        """
        if self.configs_override is not None:
            return self.configs_override
        local = self.root / "configs"
        if local.is_dir():
            return local
        packaged_config_location = Path(str(files("gptnt") / "_configs"))
        logger.debug(f"Using pre-packaged configs directory from {packaged_config_location!r}")
        return packaged_config_location

    @property
    def player_configs(self) -> Path:
        """Directory of player configs (`configs/player/`)."""
        return self.configs / "player"

    @property
    def suite_configs(self) -> Path:
        """Directory of suite configs (`configs/suites/`)."""
        return self.configs / "suites"

    @property
    def missions_library(self) -> Path:
        """Directory of materialised mission sets (`configs/missions/`)."""
        return self.configs / "missions"

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
