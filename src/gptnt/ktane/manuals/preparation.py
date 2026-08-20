"""Public preparation boundary for manual compiler source files."""

from pathlib import Path

from gptnt.ktane.manuals._compiler_sources import (
    prepare_compiler_sources as _prepare_compiler_sources,
)


async def prepare_compiler_sources(cache_dir: Path) -> None:
    """Materialize the pinned source files required by the HTML compiler."""
    await _prepare_compiler_sources(cache_dir)
