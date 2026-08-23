from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import anyio
import httpx
from pydantic import BaseModel, ConfigDict, Field

from gptnt.ktane.manuals import _assets, _git
from gptnt.ktane.manuals._http import download_to_cache
from gptnt.ktane.manuals.profile import KtaneContentAppendix, KtaneContentDocument
from gptnt.ktane.manuals.progress import ProgressReporter
from gptnt.ktane.manuals.sources import KtaneContentSource

type KtaneContentRequirement = KtaneContentDocument | KtaneContentAppendix
"""A profile entry that must be resolved to a file in the KtaneContent repository."""


@dataclass(frozen=True, kw_only=True)
class KtaneContentDownload:
    """File and byte counts for cached KtaneContent sources."""

    added_files: int = 0
    added_bytes: int = 0
    cached_files: int = 0
    cached_bytes: int = 0

    def __add__(self, other: Self) -> "KtaneContentDownload":
        """Combine two download summaries."""
        return KtaneContentDownload(
            added_files=self.added_files + other.added_files,
            added_bytes=self.added_bytes + other.added_bytes,
            cached_files=self.cached_files + other.cached_files,
            cached_bytes=self.cached_bytes + other.cached_bytes,
        )


class _CatalogEntry(BaseModel):
    """The fields used from one module entry in the aggregate KtaneContent catalog."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    module_id: str | None = Field(alias="ModuleID")
    name: str = Field(alias="Name")


class KtaneContentCatalog(BaseModel):
    """The aggregate catalog used to translate module IDs into HTML filenames."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    modules: tuple[_CatalogEntry, ...] = Field(alias="KtaneModules")

    @classmethod
    def from_path(cls, path: Path) -> Self:
        """Parse the external KtaneContent catalog."""
        return cls.model_validate_json(path.read_bytes())

    @property
    def module_names(self) -> dict[str, str]:
        """Map nonempty module identifiers to their document titles."""
        return {module.module_id: module.name for module in self.modules if module.module_id}

    def filename_for(self, requirement: KtaneContentRequirement) -> str:
        """Resolve an appendix, override, or English module ID to its repository filename."""
        if isinstance(requirement, KtaneContentAppendix):
            return requirement.document
        if requirement.document is not None:
            return requirement.document

        # The aggregate catalog supplies the default English title. Translated documents can use
        # different filenames, so their profiles must name the repository page explicitly.
        if requirement.language == "en":
            return f"{self.module_names[requirement.id]}.html"
        raise ValueError(
            f"KtaneContent document {requirement.id!r} needs an explicit page for "
            f"language {requirement.language!r}"
        )


async def _download_catalog(
    source: KtaneContentSource,
    *,
    cache_dir: Path,
    reporter: ProgressReporter,
    client: httpx.AsyncClient,
) -> tuple[KtaneContentDownload, KtaneContentCatalog]:
    """Load the cached aggregate catalog, downloading it once when absent."""
    destination = cache_dir / "sources" / "ktanecontent" / "catalog" / "raw.json"
    if destination.is_file():
        size = destination.stat().st_size
        reporter.update(
            "ktanecontent:catalog",
            "KtaneContent module catalog is cached",
            completed=size,
            total=size,
        )
        return KtaneContentDownload(
            cached_files=1, cached_bytes=size
        ), KtaneContentCatalog.from_path(destination)

    size = await download_to_cache(
        client=client,
        url=str(source.catalog.url),
        destination=destination,
        progress_key="ktanecontent:catalog",
        progress_description="Downloading KtaneContent module catalog",
        reporter=reporter,
    )
    return KtaneContentDownload(added_files=1, added_bytes=size), KtaneContentCatalog.from_path(
        destination
    )


def _paths_for_requirement(
    requirement: KtaneContentRequirement,
    *,
    catalog: KtaneContentCatalog,
    repository_paths: set[str],
) -> set[str]:
    """Resolve one profile document and its metadata in the pinned repository tree."""
    filename = catalog.filename_for(requirement)
    document_path = f"HTML/{filename}"
    if document_path not in repository_paths:
        raise ValueError(f"KtaneContent has no document {filename!r}")
    selected = {document_path}
    if isinstance(requirement, KtaneContentDocument):
        metadata_path = f"JSON/{catalog.module_names[requirement.id]}.json"
        if metadata_path not in repository_paths:
            raise ValueError(f"KtaneContent has no metadata {metadata_path!r}")
        selected.add(metadata_path)
    return selected


def _resolve_document_paths(
    requirements: Sequence[KtaneContentRequirement],
    *,
    catalog: KtaneContentCatalog,
    repository_paths: set[str],
) -> set[str]:
    """Resolve requested profile documents and confirm they exist in the pinned tree."""
    selected: set[str] = set()
    for requirement in requirements:
        selected.update(
            _paths_for_requirement(requirement, catalog=catalog, repository_paths=repository_paths)
        )
    return selected


def _discover_dependency_paths(
    repository_dir: Path, *, batch: Sequence[str], repository_paths: set[str]
) -> set[str]:
    """Find repository files referenced by one newly restored batch of assets."""
    discovered: set[str] = set()
    for source_path in batch:
        for reference in _assets.extract_references_from_file(repository_dir / source_path):
            resolved = _assets.resolve_repository_reference(
                source_path, reference, repository_paths=repository_paths
            )
            if resolved is not None:
                discovered.add(resolved)
    return discovered


async def _restore_dependency_batch(
    repository_dir: Path,
    *,
    commit: str,
    selected: set[str],
    pending: set[str],
    restored: set[str],
    repository_paths: set[str],
    reporter: ProgressReporter,
) -> set[str]:
    """Restore one dependency layer, then continue with references discovered in it."""
    if not pending:
        reporter.update(
            "ktanecontent",
            "Selected KtaneContent assets are cached",
            completed=len(selected),
            total=len(selected),
        )
        return selected

    batch = sorted(pending)
    reporter.update(
        "ktanecontent",
        "Downloading selected KtaneContent assets",
        completed=len(restored),
        total=len(selected),
    )
    await _git.restore(anyio.Path(repository_dir), commit=commit, paths=batch)
    restored.update(batch)

    # References can themselves be CSS, JavaScript, or SVG files with further references. Only
    # the newly discovered paths form the next batch, so each repository file is restored once.
    discovered = _discover_dependency_paths(
        repository_dir, batch=batch, repository_paths=repository_paths
    )
    selected.update(discovered)
    return await _restore_dependency_batch(
        repository_dir,
        commit=commit,
        selected=selected,
        pending=discovered - restored,
        restored=restored,
        repository_paths=repository_paths,
        reporter=reporter,
    )


async def restore_repository_dependencies(
    repository_dir: Path,
    *,
    commit: str,
    paths: set[str],
    repository_paths: set[str],
    reporter: ProgressReporter,
) -> set[str]:
    """Restore selected files and every local repository dependency they reference."""
    missing = paths - repository_paths
    if missing:
        raise ValueError(f"KtaneContent repository paths do not exist: {sorted(missing)}")
    return await _restore_dependency_batch(
        repository_dir,
        commit=commit,
        selected=set(paths),
        pending=set(paths),
        restored=set(),
        repository_paths=repository_paths,
        reporter=reporter,
    )


def _materialized_repository_paths(repository_dir: Path) -> set[str]:
    """List materialized working-tree files without counting Git's internal files."""
    return {
        path.relative_to(repository_dir).as_posix()
        for path in repository_dir.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(repository_dir).parts
    }


async def download_ktane_content(
    requirements: Sequence[KtaneContentRequirement],
    *,
    source: KtaneContentSource,
    cache_dir: Path,
    reporter: ProgressReporter,
    client: httpx.AsyncClient,
) -> KtaneContentDownload:
    """Cache selected KtaneContent documents and all assets they reference recursively."""
    if not requirements:
        return KtaneContentDownload()

    # The HTTP catalog is much smaller than the repository metadata and is enough to map profile
    # module IDs to their current document filenames.
    catalog_download, catalog = await _download_catalog(
        source, cache_dir=cache_dir, reporter=reporter, client=client
    )

    # Keep one blobless clone for each pinned commit. Its tree lists every available path without
    # downloading every blob. Therefore restore then only materializes the selected dependencies.
    repository_dir = cache_dir / "sources" / "ktanecontent" / source.commit
    reporter.update("ktanecontent", "Preparing KtaneContent repository")

    await _git.prepare_repository(
        repository=str(source.repository),
        commit=source.commit,
        destination=anyio.Path(repository_dir),
    )
    before = _materialized_repository_paths(repository_dir)
    repository_paths = await _git.tree_paths(anyio.Path(repository_dir), commit=source.commit)
    documents = _resolve_document_paths(
        requirements, catalog=catalog, repository_paths=repository_paths
    )
    selected = await _restore_dependency_batch(
        repository_dir,
        commit=source.commit,
        selected=set(documents),
        pending=set(documents),
        restored=set(),
        repository_paths=repository_paths,
        reporter=reporter,
    )

    # Files already present before this operation count as cache hits. Newly restored files count
    # as additions even when Git obtained their blobs through its partial-clone remote.
    added = selected - before
    cached = selected & before
    return catalog_download + KtaneContentDownload(
        added_files=len(added),
        added_bytes=sum((repository_dir / path).stat().st_size for path in added),
        cached_files=len(cached),
        cached_bytes=sum((repository_dir / path).stat().st_size for path in cached),
    )
