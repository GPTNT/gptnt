"""Typed source inputs produced by manual profile resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Self

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.ktane.manuals.sources import OfficialPageRange

__all__ = [
    "KtaneContentModuleMetadata",
    "KtaneContentProvenance",
    "LocalInputIdentity",
    "LocalProvenance",
    "OfficialManualProvenance",
    "ResolvedDocument",
    "ResolvedKtaneContentAppendix",
    "ResolvedKtaneContentModule",
    "ResolvedLocalDocument",
    "ResolvedOfficialDocument",
]


class KtaneContentModuleMetadata(BaseModel):
    """Compiler-facing fields loaded from a KtaneContent module JSON file."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    module_id: str = Field(alias="ModuleID")
    name: str = Field(alias="Name")
    origin: str = Field(alias="Origin")
    sort_key: str = Field(alias="SortKey")
    rule_seed_support: str | None = Field(alias="RuleSeedSupport", default=None)

    @classmethod
    def from_path(cls, path: Path) -> Self:
        """Parse the selected module's metadata from the pinned repository tree."""
        return cls.model_validate_json(path.read_bytes())


@dataclass(frozen=True, kw_only=True)
class KtaneContentProvenance:
    """Pinned repository inputs selected for one KtaneContent document."""

    commit: str
    document: str
    metadata_document: str | None = None


@dataclass(frozen=True, kw_only=True)
class OfficialManualProvenance:
    """Configured official manual version and download location."""

    version: str
    url: str


@dataclass(frozen=True, kw_only=True)
class LocalInputIdentity:
    """Configured-root path and content digest for one local source input."""

    path: str
    sha256: str


@dataclass(frozen=True, kw_only=True)
class LocalProvenance:
    """Every local file whose contents determine the resolved document."""

    inputs: tuple[LocalInputIdentity, ...]


@dataclass(frozen=True, kw_only=True)
class ResolvedKtaneContentModule:
    """HTML and module metadata selected from a pinned KtaneContent revision."""

    logical_id: str
    language: str
    source: Literal["ktanecontent"]
    source_path: Path
    metadata_path: Path
    metadata: KtaneContentModuleMetadata
    provenance: KtaneContentProvenance
    can_represent_rule_seed: bool


@dataclass(frozen=True, kw_only=True)
class ResolvedKtaneContentAppendix:
    """Explicit appendix HTML selected from a pinned KtaneContent revision."""

    logical_id: str
    language: str
    source: Literal["ktanecontent"]
    source_path: Path
    provenance: KtaneContentProvenance
    can_represent_rule_seed: bool


@dataclass(frozen=True, kw_only=True)
class ResolvedOfficialDocument:
    """One logical document mapped to inclusive pages in an official PDF."""

    logical_id: str
    language: str
    source: Literal["official"]
    source_path: Path
    page_range: OfficialPageRange
    provenance: OfficialManualProvenance
    can_represent_rule_seed: bool


@dataclass(frozen=True, kw_only=True)
class ResolvedLocalDocument:
    """Local HTML input with the identity of every recursively referenced file."""

    logical_id: str
    language: str
    source: Literal["local"]
    source_path: Path
    provenance: LocalProvenance
    can_represent_rule_seed: bool


type ResolvedDocument = (
    ResolvedKtaneContentModule
    | ResolvedKtaneContentAppendix
    | ResolvedOfficialDocument
    | ResolvedLocalDocument
)
"""One typed, validated compilation input in profile order."""
