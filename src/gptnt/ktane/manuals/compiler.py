"""Compile and cache model-ready manual text and page images."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gptnt.ktane.manuals._compile import compile_canonical
from gptnt.ktane.manuals._variant import prepare_variant
from gptnt.ktane.manuals.artifact import (
    CompiledManualArtifact,
    CompiledManualPage,
    ManualCompilationError,
    PreparedManualVariant,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from gptnt.ktane.manuals.profile import ManualProfile
    from gptnt.ktane.manuals.resolution import ResolvedDocument

__all__ = [
    "CompiledManualArtifact",
    "CompiledManualPage",
    "ManualCompilationError",
    "PreparedManualVariant",
    "compile_manual",
    "prepare_manual_variant",
]


def compile_manual(
    profile: ManualProfile, resolved_documents: Sequence[ResolvedDocument], *, cache_dir: Path
) -> CompiledManualArtifact:
    """Return a validated canonical artifact for ordered resolved manual inputs.

    `profile` supplies the selected documents and their prompt order. `resolved_documents` supplies
    the materialized HTML/PDF paths and source provenance in that order. The returned reference
    contains absolute paths to per-page UTF-8 text and canonical PNG files. A build is written
    outside its final content-addressed directory and published only after its manifest and files
    validate. Missing, partial, malformed, or hash-mismatched cached artifacts are replaced from
    the supplied inputs before a reference is returned.
    """
    return compile_canonical(profile, resolved_documents, cache_dir=cache_dir)


def prepare_manual_variant(
    artifact: CompiledManualArtifact, *, width: int, height: int
) -> PreparedManualVariant:
    """Return cached page images resized from a validated canonical manual.

    Width and height must be positive pixel counts. Variant identity contains the canonical
    artifact digest, requested dimensions, and resizer version. Publication is atomic and a stale
    variant is rebuilt beneath the canonical artifact. Canonical text and images are neither copied
    nor rebuilt.
    """
    return prepare_variant(artifact, width=width, height=height)
