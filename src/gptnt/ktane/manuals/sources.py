import tomllib
from pathlib import Path
from typing import Literal, Self

from pydantic import AnyUrl, BaseModel, ConfigDict, HttpUrl


class KtaneContentCatalogSource(BaseModel):
    """Aggregate module metadata published by KtaneContent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: HttpUrl


class KtaneContentSource(BaseModel):
    """KtaneContent repository revision used to resolve community documents."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    repository: AnyUrl
    commit: str
    catalog: KtaneContentCatalogSource


class OfficialManualSource(BaseModel):
    """One language and version of the official Bomb Defusal Manual."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    url: HttpUrl


class ManualSources(BaseModel):
    """Complete pinned source configuration for manual downloads."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    ktane_content: KtaneContentSource
    official_manual: dict[str, OfficialManualSource]

    @classmethod
    def from_path(cls, path: Path) -> Self:
        """Parse and validate a TOML source configuration."""
        return cls.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
