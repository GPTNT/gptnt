"""Compile ordered resolved documents into cached manual artifacts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gptnt.ktane.manuals._compiler import ManualCompileError as _ManualCompileError
from gptnt.ktane.manuals.artifacts import compile_manual as _compile_manual

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from gptnt.ktane.manuals.artifacts import ManualArtifact
    from gptnt.ktane.manuals.resolution import ResolvedDocument

ManualCompileError = _ManualCompileError


def compile_manual(documents: Sequence[ResolvedDocument], *, cache_dir: Path) -> ManualArtifact:
    """Compile an ordered resolved-document sequence into a loaded manual artifact."""
    return _compile_manual(documents, cache_dir=cache_dir)
