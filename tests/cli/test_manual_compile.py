"""CLI selection and orchestration for standalone manual compilation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from gptnt.cli.manual import compile as command, selection
from gptnt.ktane.manuals.profile import KtaneContentAppendix, ManualProfile

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


@pytest.mark.anyio
async def test_compile_reuses_selection_and_orders_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deduplicate suite profiles and pass them to the shared preparation boundary."""
    profile = ManualProfile(
        include_frontmatter=False,
        documents=(
            KtaneContentAppendix(source="ktanecontent", language="en", document="Wires.html"),
        ),
    )
    captured_profiles: list[ManualProfile] = []

    # Local fakes record the orchestration order without crossing browser or network boundaries.
    def compose_suite(_: str) -> SimpleNamespace:  # noqa: WPS430
        """Return the one configured profile used by this orchestration fixture."""
        return SimpleNamespace(manual_profile=profile)

    async def prepare(  # noqa: WPS430
        profiles: Sequence[ManualProfile], **_kwargs: object
    ) -> dict[ManualProfile, SimpleNamespace]:
        """Record profiles selected by the command and return one prepared path."""
        captured_profiles.extend(profiles)
        return dict(zip((profile,), (SimpleNamespace(path=tmp_path / "artifact"),), strict=True))

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
    monkeypatch.setattr(command, "ManualSources", SimpleNamespace(from_path=lambda _: object()))
    monkeypatch.setattr(command, "prepare_manual_artifacts", prepare)

    await command.compile_manuals(suites=["one", "two", "one"])

    assert captured_profiles == [profile]
