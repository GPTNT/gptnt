"""Stored manifest models and validation for compiled manual artifacts."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Literal, Self

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

if TYPE_CHECKING:
    from pathlib import Path

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_ARTIFACT_DIGEST_PATTERN = r"^[0-9a-f]{32}$"


class RendererIdentity(BaseModel):
    """Runtime renderers whose versions can change canonical page output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    html: str
    pages: str


class ResizerIdentity(BaseModel):
    """Runtime image resizer whose version can change a prepared variant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    implementation: str
    algorithm: str


class ResolvedInputManifest(BaseModel):
    """Content and provenance identity of one ordered resolved document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_index: int = Field(ge=0)
    document_id: str
    source: Literal["ktanecontent", "official", "local"]
    language: str
    supports_requested_rule_seed: bool
    provenance: JsonValue
    source_sha256: str = Field(pattern=_SHA256_PATTERN)
    metadata_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    first_page: int | None = Field(default=None, gt=0)
    last_page: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _require_complete_page_range(self) -> Self:
        if (self.first_page is None) != (self.last_page is None):
            raise ValueError("first_page and last_page must either both be set or both be absent")
        if (
            self.first_page is not None
            and self.last_page is not None
            and self.last_page < self.first_page
        ):
            raise ValueError("last_page must be greater than or equal to first_page")
        return self


class PageManifest(BaseModel):
    """One canonical page in prompt order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page_number: int = Field(gt=0)
    document_index: int = Field(ge=0)
    document_page_number: int = Field(gt=0)
    document_id: str
    source: Literal["ktanecontent", "official", "local"]
    provenance: JsonValue
    text_path: str
    text_sha256: str = Field(pattern=_SHA256_PATTERN)
    image_path: str
    image_sha256: str = Field(pattern=_SHA256_PATTERN)


class ArtifactManifest(BaseModel):
    """Completion record for one canonical compiled manual."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    compiler_schema: str
    rule_seed: int = Field(gt=0)
    renderer: RendererIdentity
    artifact_digest: str = Field(pattern=_ARTIFACT_DIGEST_PATTERN)
    profile: JsonValue
    resolved_inputs: tuple[ResolvedInputManifest, ...]
    pages: tuple[PageManifest, ...]

    @model_validator(mode="after")
    def _require_ordered_entries(self) -> Self:
        input_indexes = [source.document_index for source in self.resolved_inputs]
        if input_indexes != list(range(len(input_indexes))):
            raise ValueError("resolved input indexes must be contiguous and ordered")
        page_numbers = [page.page_number for page in self.pages]
        if page_numbers != list(range(1, len(page_numbers) + 1)):
            raise ValueError("page numbers must be contiguous and ordered")
        if not self.pages:
            raise ValueError("a compiled manual must contain at least one page")
        for page in self.pages:
            _validate_page_source(page, sources=self.resolved_inputs)
        return self


class VariantPageManifest(BaseModel):
    """One resized page derived from a canonical page."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page_number: int = Field(gt=0)
    image_path: str
    image_sha256: str = Field(pattern=_SHA256_PATTERN)


class VariantManifest(BaseModel):
    """Completion record for one image-dimension variant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    canonical_artifact_digest: str = Field(pattern=_ARTIFACT_DIGEST_PATTERN)
    variant_digest: str = Field(pattern=_ARTIFACT_DIGEST_PATTERN)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    resizer: ResizerIdentity
    pages: tuple[VariantPageManifest, ...]

    @model_validator(mode="after")
    def _require_ordered_pages(self) -> Self:
        page_numbers = [page.page_number for page in self.pages]
        if page_numbers != list(range(1, len(page_numbers) + 1)):
            raise ValueError("variant page numbers must be contiguous and ordered")
        if not self.pages:
            raise ValueError("a prepared manual variant must contain at least one page")
        return self


def sha256_file(path: Path) -> str:
    """Hash a stored source or artifact file without loading it as text."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_page_source(
    page: PageManifest, *, sources: tuple[ResolvedInputManifest, ...]
) -> None:
    """Require each page to repeat the identity of its selected source."""
    try:
        source = sources[page.document_index]
    except IndexError as error:
        raise ValueError(f"page {page.page_number} refers to an absent resolved input") from error
    page_identity = page.document_id, page.source, page.provenance
    source_identity = source.document_id, source.source, source.provenance
    if page_identity != source_identity:
        raise ValueError(f"page {page.page_number} does not match its resolved input identity")


def artifact_path(root: Path, relative_path: str) -> Path:
    """Resolve a manifest path while rejecting paths outside its artifact root."""
    candidate = (root / relative_path).resolve()
    try:
        _ = candidate.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(
            f"artifact path {relative_path!r} leaves its artifact directory"
        ) from error
    return candidate


def validate_artifact_files(root: Path, manifest: ArtifactManifest) -> None:
    """Check every canonical file named by a parsed manifest."""
    for page in manifest.pages:
        text_path = artifact_path(root, page.text_path)
        image_path = artifact_path(root, page.image_path)
        if sha256_file(text_path) != page.text_sha256:
            raise ValueError(f"compiled page {page.page_number} text hash does not match")
        _ = text_path.read_text(encoding="utf-8")
        if sha256_file(image_path) != page.image_sha256:
            raise ValueError(f"compiled page {page.page_number} image hash does not match")
        _validate_png(image_path, expected_size=None)


def validate_variant_files(root: Path, manifest: VariantManifest) -> None:
    """Check every resized image named by a parsed variant manifest."""
    for page in manifest.pages:
        image_path = artifact_path(root, page.image_path)
        if sha256_file(image_path) != page.image_sha256:
            raise ValueError(f"prepared page {page.page_number} image hash does not match")
        _validate_png(image_path, expected_size=(manifest.width, manifest.height))


def _validate_png(path: Path, *, expected_size: tuple[int, int] | None) -> None:
    """Decode one PNG and optionally check its prepared dimensions."""
    with Image.open(path, formats=("PNG",)) as image:
        _ = image.load()
        if expected_size is not None and image.size != expected_size:
            raise ValueError(
                f"prepared image {path.name!r} has size {image.size}, not {expected_size}"
            )
