"""CLI selection and orchestration for standalone manual compilation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from gptnt.cli.manual import compile as command, selection
from gptnt.ktane.manuals.download import DownloadResult
from gptnt.ktane.manuals.profile import KtaneContentAppendix, ManualProfile
from gptnt.ktane.manuals.resolution import OfficialManualProvenance, ResolvedOfficialDocument
from gptnt.ktane.manuals.sources import (
    KtaneContentCatalogSource,
    KtaneContentSource,
    ManualSources,
    OfficialPageRange,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path


@pytest.mark.anyio
async def test_compile_reuses_selection_and_orders_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deduplicate suite profiles and run download, resolve, then compile without Chromium."""
    profile = ManualProfile(
        include_frontmatter=False,
        documents=(
            KtaneContentAppendix(source="ktanecontent", language="en", document="Wires.html"),
        ),
    )
    sources = ManualSources(
        ktane_content=KtaneContentSource(
            repository="https://content.test/repository.git",
            commit="1" * 40,
            catalog=KtaneContentCatalogSource(url="https://content.test/catalog"),
        ),
        official_manual={},
    )
    resolved = ResolvedOfficialDocument(
        document_id="Fixture",
        language="en",
        source="official",
        source_path=tmp_path / "unused.pdf",
        page_range=OfficialPageRange(first=1, last=1),
        provenance=OfficialManualProvenance(version="1", url="https://manual.test/a.pdf"),
        supports_requested_rule_seed=True,
    )
    operations: list[str] = []
    captured_profiles: list[ManualProfile] = []

    # Local fakes record the orchestration order without crossing browser or network boundaries.
    def compose_suite(_: str) -> SimpleNamespace:  # noqa: WPS430
        """Return the one configured profile used by this orchestration fixture."""
        return SimpleNamespace(manual_profile=profile)

    async def download(  # noqa: WPS430
        profiles: Sequence[ManualProfile], **_kwargs: object
    ) -> DownloadResult:
        """Record download order and the profiles selected by the command."""
        operations.append("download")
        captured_profiles.extend(profiles)
        return DownloadResult(
            cache_dir=tmp_path, added_files=0, added_bytes=0, cached_files=0, cached_bytes=0
        )

    def resolve(  # noqa: WPS430
        *_args: object, **_kwargs: object
    ) -> tuple[ResolvedOfficialDocument, ...]:
        """Record resolution and return an official-only resolved profile."""
        operations.append("resolve")
        return (resolved,)

    def compile_manual(*_args: object, **_kwargs: object) -> Path:  # noqa: WPS430
        """Record compilation without creating a browser or artifact."""
        operations.append("compile")
        return tmp_path / "artifact"

    async def run_sync(function: Callable[[], Path]) -> Path:  # noqa: WPS430
        """Execute the supplied synchronous compiler callable in the test task."""
        return function()

    # Patch every external boundary so the assertion isolates CLI selection and ordering.
    monkeypatch.setattr(selection, "discover_suites", lambda: ["one", "two"])
    monkeypatch.setattr(selection, "compose_suite", compose_suite)
    monkeypatch.setattr(
        command,
        "paths",
        SimpleNamespace(
            manual_sources=tmp_path / "sources.toml",
            manual_cache=tmp_path / "cache",
            root=tmp_path,
        ),
    )
    monkeypatch.setattr(command, "ManualSources", SimpleNamespace(from_path=lambda _: sources))
    monkeypatch.setattr(command, "download_manual_assets", download)
    monkeypatch.setattr(command, "resolve_manual_profile", resolve)
    monkeypatch.setattr(command, "compile_manual", compile_manual)
    monkeypatch.setattr(command, "run_sync", run_sync)

    await command.compile_manuals(suites=["one", "two", "one"])

    assert captured_profiles == [profile]
    assert operations == ["download", "resolve", "compile"]
