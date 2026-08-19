"""Public references to validated compiled manual artifacts."""

from dataclasses import dataclass
from pathlib import Path


class ManualCompilationError(ValueError):
    """A selected profile or resolved source cannot be compiled."""


@dataclass(frozen=True, kw_only=True)
class CompiledManualPage:
    """Absolute paths to the text and canonical image for one ordered page."""

    page_number: int
    document_id: str
    document_page_number: int
    text_path: Path
    image_path: Path


@dataclass(frozen=True, kw_only=True)
class CompiledManualArtifact:
    """Validated reference to one content-addressed canonical manual."""

    digest: str
    path: Path
    pages: tuple[CompiledManualPage, ...]


@dataclass(frozen=True, kw_only=True)
class PreparedManualVariant:
    """Validated resized page images that retain one canonical artifact's text."""

    digest: str
    path: Path
    canonical: CompiledManualArtifact
    image_paths: tuple[Path, ...]
