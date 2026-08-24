"""CLI behavior for selecting and downloading manual profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
import yaml

from gptnt.cli.manual import _selection as selection, download as command
from gptnt.ktane.manuals.download import DownloadResult
from gptnt.ktane.manuals.profile import KtaneContentAppendix, ManualProfile

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from gptnt.ktane.manuals.progress import ProgressCallback
    from gptnt.ktane.manuals.sources import ManualSources


def _profile(document: str = "Wires.html") -> ManualProfile:
    """Build a distinct manual profile identified by one appendix filename."""
    return ManualProfile(
        include_frontmatter=False,
        documents=(KtaneContentAppendix(source="ktanecontent", language="en", document=document),),
    )


@dataclass(kw_only=True)
class _SuiteComposer:
    """Return configured suite profiles while recording suite composition order."""

    profiles: dict[str, ManualProfile]
    composed: list[str] = field(default_factory=list)

    def __call__(self, suite_name: str) -> SimpleNamespace:
        """Record and compose one requested suite name."""
        self.composed.append(suite_name)
        return SimpleNamespace(manual_profile=self.profiles[suite_name])


@dataclass(kw_only=True)
class _DownloadRecorder:
    """Capture the profiles passed through the CLI-to-downloader boundary."""

    captured_profiles: list[ManualProfile] = field(default_factory=list)

    async def __call__(
        self,
        profiles: Sequence[ManualProfile],
        *,
        sources: ManualSources,
        cache_dir: Path,
        root_dir: Path,
        progress: ProgressCallback,
    ) -> DownloadResult:
        """Record selected profiles and return a deterministic download summary."""
        _ = sources, root_dir, progress
        self.captured_profiles.extend(profiles)
        return DownloadResult(
            cache_dir=cache_dir, added_files=2, added_bytes=20, cached_files=1, cached_bytes=10
        )


@pytest.mark.anyio
async def test_download_without_suite_uses_all_suites_and_deduplicates_profiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use every discovered suite by default and download each shared profile once."""
    shared_profile = _profile()
    other_profile = _profile("Keypad.html")

    # The first two suites intentionally share a profile so the command's profile-level
    # deduplication is observable independently of suite discovery.
    composer = _SuiteComposer(
        profiles={"one": shared_profile, "two": shared_profile, "three": other_profile}
    )
    download = _DownloadRecorder()

    monkeypatch.setattr(selection, "discover_suites", lambda: ["one", "two", "three"])
    monkeypatch.setattr(selection, "compose_suite", composer)
    monkeypatch.setattr(command, "download_manual_assets", download)

    await command.download()

    assert composer.composed == ["one", "two", "three"]
    assert download.captured_profiles == [shared_profile, other_profile]


@pytest.mark.anyio
async def test_download_with_suites_only_composes_selected_suites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compose only explicitly selected suites while preserving first-occurrence order."""
    selected_profile = _profile()
    composer = _SuiteComposer(profiles={"one": selected_profile, "two": selected_profile})
    download = _DownloadRecorder()

    monkeypatch.setattr(selection, "discover_suites", lambda: ["one", "two"])
    monkeypatch.setattr(selection, "compose_suite", composer)
    monkeypatch.setattr(command, "download_manual_assets", download)

    # Repeating "two" verifies suite names are deduplicated before composition.
    await command.download(suites=["two", "one", "two"])

    assert composer.composed == ["two", "one"]
    assert download.captured_profiles == [selected_profile]


@pytest.mark.anyio
async def test_download_all_profiles_includes_profiles_unused_by_suites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Load every configured profile file without consulting suite configuration."""
    vanilla = _profile()
    unused = _profile("Unused.html")

    # Use serialized YAML files so this test covers the same configuration boundary as the CLI.
    profile_paths = [tmp_path / "a-vanilla.yaml", tmp_path / "b-unused.yaml"]
    for profile_path, profile in zip(profile_paths, (vanilla, unused), strict=True):
        _ = profile_path.write_text(
            yaml.safe_dump(profile.model_dump(mode="json")), encoding="utf-8"
        )
    download = _DownloadRecorder()

    monkeypatch.setattr(
        command,
        "paths",
        SimpleNamespace(
            manual_profiles=tmp_path,
            manual_sources=command.paths.manual_sources,
            manual_cache=command.paths.manual_cache,
            root=command.paths.root,
        ),
    )
    monkeypatch.setattr(
        selection,
        "discover_suites",
        # All-profile selection must still work when suite discovery is unavailable.
        lambda: pytest.fail("suite discovery must not run with --all-profiles"),
    )

    monkeypatch.setattr(command, "download_manual_assets", download)

    await command.download(all_profiles=True)

    assert download.captured_profiles == [vanilla, unused]


@pytest.mark.anyio
async def test_download_rejects_unknown_suite(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject unknown suite names and report the suites available to the user."""
    monkeypatch.setattr(selection, "discover_suites", lambda: ["known"])

    with pytest.raises(ValueError, match=r"unknown suites \['missing'\]; available: \['known'\]"):
        await command.download(suites=["known", "missing"])


@pytest.mark.anyio
async def test_download_rejects_suites_with_all_profiles() -> None:
    """Reject conflicting suite and all-profile selection modes."""
    with pytest.raises(ValueError, match="--all-profiles cannot be combined with --suite"):
        await command.download(suites=["known"], all_profiles=True)
