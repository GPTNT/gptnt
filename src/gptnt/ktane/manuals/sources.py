import tomllib
from pathlib import Path
from typing import Literal, Self

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, HttpUrl, model_validator

from gptnt.ktane.manuals.profile import Document


class KtaneContentCatalogSource(BaseModel):
    """Aggregate module metadata published by KtaneContent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: HttpUrl
    """Download location for the aggregate module and translated-filename catalog."""


class KtaneContentSource(BaseModel):
    """KtaneContent repository revision used to resolve community documents."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    repository: AnyUrl
    """Git repository from which KtaneContent documents and assets are downloaded."""

    commit: str = Field(pattern=r"^[0-9a-fA-F]{40}$")
    """Exact repository commit included in cache paths and artifact provenance."""

    catalog: KtaneContentCatalogSource
    """Catalog used to resolve module identifiers and translated document filenames."""


class OfficialManualSource(BaseModel):
    """One language and version of the official Bomb Defusal Manual."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    """Manual version included in the cache location and artifact provenance."""

    url: HttpUrl
    """Download location for the official manual in the configured language."""

    pages: dict[str, "OfficialPageRange"] = Field(default_factory=dict)
    """Pages to extract for each profile document ID available in this PDF."""

    def cache_path(self, language: str, *, cache_dir: Path) -> Path:
        """Return the cache location shared by download and profile resolution."""
        return cache_dir / "sources" / "official" / language / self.version / "manual.pdf"


class OfficialPageRange(BaseModel):
    """First and last PDF pages to extract for one profile document.

    PDF page numbering starts at 1. Both `first` and `last` are included, so a document contained
    on one page uses the same value for both fields.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    first: int = Field(gt=0)
    last: int = Field(gt=0)

    @model_validator(mode="after")
    def _require_ordered_pages(self) -> Self:
        """Reject an interval whose final page precedes its first page."""
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
    """Official-manual sources keyed by language code."""

    @classmethod
    def from_path(cls, path: Path) -> Self:
        """Parse and validate a TOML source configuration."""
        return cls.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
