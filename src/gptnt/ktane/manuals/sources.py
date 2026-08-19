import tomllib
from pathlib import Path
from typing import Literal, Self

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, HttpUrl, model_validator

from gptnt.ktane.manuals.profile import Document


class KtaneContentCatalogSource(BaseModel):
    """Aggregate module metadata published by KtaneContent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: HttpUrl


class KtaneContentSource(BaseModel):
    """KtaneContent repository revision used to resolve community documents."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    repository: AnyUrl
    commit: str = Field(pattern=r"^[0-9a-fA-F]{40}$")
    catalog: KtaneContentCatalogSource


class OfficialManualSource(BaseModel):
    """One language and version of the official Bomb Defusal Manual."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    url: HttpUrl
    pages: dict[str, "OfficialPageRange"] = Field(default_factory=dict)
    """One-based inclusive page ranges keyed by the profile document ID."""

    def cache_path(self, language: str, *, cache_dir: Path) -> Path:
        """Return the cache location shared by download and profile resolution."""
        return cache_dir / "sources" / "official" / language / self.version / "manual.pdf"


class OfficialPageRange(BaseModel):
    """One-based inclusive pages occupied by one logical official-manual document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    first: int = Field(gt=0)
    last: int = Field(gt=0)

    @model_validator(mode="after")
    def _require_ordered_pages(self) -> Self:
        if self.last < self.first:
            raise ValueError("last page must be greater than or equal to first page")
        return self


class ManualSources(BaseModel):
    """Complete pinned source configuration for manual downloads."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    ktane_content: KtaneContentSource
    frontmatter: tuple[Document, ...] = ()
    """Configured source documents inserted before a profile when frontmatter is enabled."""
    official_manual: dict[str, OfficialManualSource]

    @classmethod
    def from_path(cls, path: Path) -> Self:
        """Parse and validate a TOML source configuration."""
        return cls.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
