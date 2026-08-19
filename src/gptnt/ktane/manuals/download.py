"""Download and cache the source files selected by manual profiles."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

from gptnt.common.base_client import cached_retrying_async_http_client
from gptnt.ktane.manuals import _ktane_content
from gptnt.ktane.manuals._http import download_to_cache
from gptnt.ktane.manuals._progress import DownloadProgress, ProgressCallback, ProgressReporter
from gptnt.ktane.manuals.profile import (
    Document,
    KtaneContentAppendix,
    KtaneContentDocument,
    ManualProfile,
    OfficialDocument,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    import httpx

    from gptnt.ktane.manuals.sources import KtaneContentSource, ManualSources, OfficialManualSource

__all__ = ["DownloadProgress", "DownloadResult", "ProgressCallback", "download_manual_assets"]


@dataclass(frozen=True, kw_only=True)
class DownloadResult:
    """File and byte counts from one cache operation."""

    cache_dir: Path
    added_files: int
    added_bytes: int
    cached_files: int
    cached_bytes: int

    @classmethod
    def empty(cls, cache_dir: Path) -> Self:
        """Create a result for a plan that requires no remote assets."""
        return cls(
            cache_dir=cache_dir, added_files=0, added_bytes=0, cached_files=0, cached_bytes=0
        )


@dataclass(frozen=True, kw_only=True)
class _OfficialAsset:
    """Official PDF URL and cache destination selected for one language."""

    language: str
    url: str
    destination: Path

    @classmethod
    def from_source(cls, language: str, source: OfficialManualSource, *, cache_dir: Path) -> Self:
        """Resolve one configured official manual to its cache destination."""
        return cls(
            language=language,
            url=str(source.url),
            destination=source.cache_path(language, cache_dir=cache_dir),
        )


@dataclass(kw_only=True)
class _ProfileSelection:
    """Distinct remote sources and validated local files required by a profile set."""

    ktane_documents: set[_ktane_content.KtaneContentRequirement] = field(default_factory=set)
    official_languages: set[str] = field(default_factory=set)

    @classmethod
    def from_profiles(cls, profiles: Sequence[ManualProfile], *, root_dir: Path) -> Self:
        """Collect and validate the distinct documents selected by profiles."""
        selection = cls()
        for profile in profiles:
            for document in profile.documents:
                selection.update_document(document, root_dir=root_dir)
        return selection

    def include_frontmatter(self, documents: Sequence[Document], *, root_dir: Path) -> None:
        """Include configured frontmatter required by at least one selected profile."""
        for document in documents:
            self.update_document(document, root_dir=root_dir)

    @property
    def ordered_ktane_documents(self) -> tuple[_ktane_content.KtaneContentRequirement, ...]:
        """Return selected KtaneContent documents in deterministic order."""
        return tuple(sorted(self.ktane_documents, key=lambda document: document.model_dump_json()))

    def update_document(self, document: Document, *, root_dir: Path) -> None:
        """Add one profile document to this selection."""
        if isinstance(document, OfficialDocument):
            self.official_languages.add(document.language)
        elif isinstance(document, (KtaneContentDocument, KtaneContentAppendix)):
            self.ktane_documents.add(document)
        else:
            local_path = document.path if document.path.is_absolute() else root_dir / document.path
            if not local_path.is_file():
                raise ValueError(f"local manual document does not exist: {local_path}")


@dataclass(frozen=True, kw_only=True)
class _DownloadPlan:
    """Remote assets to cache before any selected profile can be resolved."""

    cache_dir: Path
    ktane_source: KtaneContentSource
    ktane_documents: tuple[_ktane_content.KtaneContentRequirement, ...]
    official_assets: tuple[_OfficialAsset, ...]

    @classmethod
    def from_profiles(
        cls,
        profiles: Sequence[ManualProfile],
        *,
        sources: ManualSources,
        cache_dir: Path,
        root_dir: Path,
    ) -> Self:
        """Resolve validated profiles and source configuration into one download plan."""
        if not profiles:
            raise ValueError("at least one manual profile is required")

        selection = _ProfileSelection.from_profiles(profiles, root_dir=root_dir)
        # Frontmatter lives in source configuration rather than each profile, so include it once
        # when at least one selected profile requests it.
        if any(profile.include_frontmatter for profile in profiles):
            if not sources.frontmatter:
                raise ValueError(
                    "include_frontmatter is enabled but no frontmatter source is configured"
                )
            selection.include_frontmatter(sources.frontmatter, root_dir=root_dir)
        unknown_languages = selection.official_languages - set(sources.official_manual)
        if unknown_languages:
            raise ValueError(
                f"official manual sources are not configured for: {sorted(unknown_languages)}"
            )
        official_assets = tuple(
            _OfficialAsset.from_source(
                language, sources.official_manual[language], cache_dir=cache_dir
            )
            for language in sorted(selection.official_languages)
        )
        return cls(
            cache_dir=cache_dir,
            ktane_source=sources.ktane_content,
            ktane_documents=selection.ordered_ktane_documents,
            official_assets=official_assets,
        )

    @property
    def has_remote_assets(self) -> bool:
        """Whether executing this plan requires HTTP or Git access."""
        return bool(self.ktane_documents or self.official_assets)


@dataclass(frozen=True, kw_only=True)
class _OfficialDownload:
    """Cache status and byte size for one official PDF."""

    cached: bool
    size: int


async def _download_official_manual(
    asset: _OfficialAsset, *, reporter: ProgressReporter, client: httpx.AsyncClient
) -> _OfficialDownload:
    """Reuse or download one official PDF and report its complete byte count."""
    if asset.destination.is_file():
        size = asset.destination.stat().st_size
        reporter.update(
            f"official:{asset.language}",
            f"Official manual {asset.language} is cached",
            completed=size,
            total=size,
        )
        return _OfficialDownload(cached=True, size=size)

    size = await download_to_cache(
        client=client,
        url=asset.url,
        destination=asset.destination,
        progress_key=f"official:{asset.language}",
        progress_description=f"Downloading official manual {asset.language}",
        reporter=reporter,
    )
    return _OfficialDownload(cached=False, size=size)


async def _execute_plan(
    plan: _DownloadPlan, *, reporter: ProgressReporter, client: httpx.AsyncClient
) -> DownloadResult:
    """Cache a plan and combine KtaneContent and official PDF file and byte counts."""
    ktane_download = await _ktane_content.download_ktane_content(
        plan.ktane_documents,
        source=plan.ktane_source,
        cache_dir=plan.cache_dir,
        reporter=reporter,
        client=client,
    )
    official_downloads = await asyncio.gather(
        *(
            _download_official_manual(asset, reporter=reporter, client=client)
            for asset in plan.official_assets
        )
    )
    return DownloadResult(
        cache_dir=plan.cache_dir,
        added_files=ktane_download.added_files
        + sum(not download.cached for download in official_downloads),
        added_bytes=ktane_download.added_bytes
        + sum(download.size for download in official_downloads if not download.cached),
        cached_files=ktane_download.cached_files
        + sum(download.cached for download in official_downloads),
        cached_bytes=ktane_download.cached_bytes
        + sum(download.size for download in official_downloads if download.cached),
    )


async def download_manual_assets(
    profiles: Sequence[ManualProfile],
    *,
    sources: ManualSources,
    cache_dir: Path,
    root_dir: Path,
    progress: ProgressCallback | None = None,
    client: httpx.AsyncClient | None = None,
) -> DownloadResult:
    """Cache every remote source file required by the supplied manual profiles."""
    plan = _DownloadPlan.from_profiles(
        profiles, sources=sources, cache_dir=cache_dir, root_dir=root_dir
    )
    if not plan.has_remote_assets:
        return DownloadResult.empty(cache_dir)

    reporter = ProgressReporter(progress)
    download_client = client or cached_retrying_async_http_client(provider="manual-download")
    return await _execute_plan(plan, reporter=reporter, client=download_client)
