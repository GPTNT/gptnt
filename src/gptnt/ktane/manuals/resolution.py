"""Typed source inputs produced by manual profile resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.ktane.manuals.sources import OfficialPageRange


class KtaneContentModuleMetadata(BaseModel):
    """Module fields read from the JSON file beside a KtaneContent HTML document.

    KtaneContent publishes additional fields that the compiler does not consume. Those fields are
    ignored so additions to the upstream catalog do not change the resolved input contract.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    module_id: str = Field(alias="ModuleID")
    name: str = Field(alias="Name")
    origin: str = Field(alias="Origin")
    sort_key: str = Field(alias="SortKey")
    rule_seed_support: str | None = Field(alias="RuleSeedSupport", default=None)


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
    """Module HTML and JSON metadata selected from a pinned KtaneContent revision."""

    document_id: str
    language: str
    source: Literal["ktanecontent"]
    source_path: Path
    metadata_path: Path
    metadata: KtaneContentModuleMetadata
    provenance: KtaneContentProvenance
    supports_requested_rule_seed: bool


@dataclass(frozen=True, kw_only=True)
class ResolvedKtaneContentAppendix:
    """Appendix HTML selected by filename from a pinned KtaneContent revision.

    Appendices have no module ID and therefore do not require a module JSON file.
    """

    document_id: str
    language: str
    source: Literal["ktanecontent"]
    source_path: Path
    provenance: KtaneContentProvenance
    supports_requested_rule_seed: bool


@dataclass(frozen=True, kw_only=True)
class ResolvedOfficialDocument:
    """Official manual PDF and configured page interval for one profile document."""

    document_id: str
    language: str
    source: Literal["official"]
    source_path: Path
    page_range: OfficialPageRange
    provenance: OfficialManualProvenance
    supports_requested_rule_seed: bool


@dataclass(frozen=True, kw_only=True)
class ResolvedLocalDocument:
    """Local HTML and the path and digest of every file in its dependency graph."""

    document_id: str
    language: str
    source: Literal["local"]
    source_path: Path
    provenance: LocalProvenance
    supports_requested_rule_seed: bool


type ResolvedDocument = (
    ResolvedKtaneContentModule
    | ResolvedKtaneContentAppendix
    | ResolvedOfficialDocument
    | ResolvedLocalDocument
)
"""One typed, validated compilation input in profile order."""
