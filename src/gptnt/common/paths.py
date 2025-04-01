from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Paths(BaseSettings):
    """Paths and locations for things."""

    root: Path = Field(default_factory=Path.cwd, description="Project root")

    configs: Path = Field(
        default_factory=lambda: Path.cwd().joinpath("configs").resolve(),
        description="All Hydra configs",
    )
    storage: Path = Field(
        default_factory=lambda: Path.cwd().joinpath("storage").resolve(),
        description="Local storage dir",
    )
