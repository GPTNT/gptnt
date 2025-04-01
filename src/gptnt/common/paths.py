from pathlib import Path

from pydantic import Field, HttpUrl
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


class KtanePaths(Paths):
    """Paths and locations for KTANE."""

    manual_local: Path = Field(
        default_factory=lambda: Paths.storage.joinpath("manual").resolve(),
        description="Path to the manual",
    )

    manual_remote: HttpUrl = HttpUrl(
        "https://www.bombmanual.com/print/KeepTalkingAndNobodyExplodes-BombDefusalManual-v1.pdf"
    )
