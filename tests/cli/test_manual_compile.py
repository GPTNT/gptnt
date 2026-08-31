"""CLI selection and orchestration for standalone manual compilation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from gptnt.cli.manual import _selection as selection, compile as command
from gptnt.common.paths import Paths
from gptnt.ktane.manuals.profile import KtaneContentAppendix, ManualProfile
from gptnt.ktane.manuals.requirement import ManualRequirement

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


@pytest.mark.anyio
async def test_compile_reuses_selection_and_orders_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deduplicate matching suite requirements before preparation."""
    profile = ManualProfile(
        include_frontmatter=False,
        documents=(
            KtaneContentAppendix(source="ktanecontent", language="en", document="Wires.html"),
        ),
    )
    captured_requirements: list[ManualRequirement] = []

    # Local fakes record the orchestration order without crossing browser or network boundaries.
    def compose_suite(_: str) -> SimpleNamespace:  # noqa: WPS430
        """Return the one configured profile used by this orchestration fixture."""
        return SimpleNamespace(manual_profile=profile, manual_rule_seed=1)

    async def prepare(  # noqa: WPS430
        requirements: Sequence[ManualRequirement], **_kwargs: object
    ) -> dict[ManualRequirement, SimpleNamespace]:
        """Record requirements selected by the command and return one prepared path."""
        captured_requirements.extend(requirements)
        requirement = ManualRequirement(profile=profile, rule_seed=1)
        return {requirement: SimpleNamespace(path=tmp_path / "artifact")}

    async def download_assets(*_args: object, **_kwargs: object) -> None:  # noqa: WPS430
        """Skip external source-cache work in this command test."""

    # Patch every external boundary so the assertion isolates CLI selection and ordering.
    monkeypatch.setattr(selection, "discover_suites", lambda: ["one", "two"])
    monkeypatch.setattr(selection, "compose_suite", compose_suite)
    monkeypatch.setattr(
        command,
        "paths",
        SimpleNamespace(
            manual_sources=tmp_path / "sources.toml",
            manual_profiles=tmp_path / "manual",
            manual_cache=tmp_path / "cache",
            root=tmp_path,
        ),
    )
    monkeypatch.setattr(command, "ManualSources", SimpleNamespace(from_path=lambda _: object()))
    monkeypatch.setattr(command, "download_manual_assets", download_assets)
    monkeypatch.setattr(command, "compile_manual_artifacts", prepare)

    await command.compile_manuals(suites=["one", "two", "one"])

    assert captured_requirements == [ManualRequirement(profile=profile, rule_seed=1)]


@pytest.mark.anyio
async def test_compile_keeps_distinct_rule_seeds_for_a_shared_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Suite selection must not collapse manuals that need different generated rules."""
    profile = ManualProfile(
        include_frontmatter=False,
        documents=(
            KtaneContentAppendix(source="ktanecontent", language="en", document="Wires.html"),
        ),
    )
    captured_requirements: list[ManualRequirement] = []

    def compose_suite(suite_name: str) -> SimpleNamespace:  # noqa: WPS430
        return SimpleNamespace(
            manual_profile=profile, manual_rule_seed={"one": 1, "two": 2}[suite_name]
        )

    async def prepare(  # noqa: WPS430
        requirements: Sequence[ManualRequirement], **_kwargs: object
    ) -> dict[ManualRequirement, SimpleNamespace]:
        captured_requirements.extend(requirements)
        return {
            requirement: SimpleNamespace(path=tmp_path / f"artifact-{requirement.rule_seed}")
            for requirement in requirements
        }

    async def download_assets(*_args: object, **_kwargs: object) -> None:  # noqa: WPS430
        """Skip external source-cache work in this command test."""

    monkeypatch.setattr(selection, "discover_suites", lambda: ["one", "two"])
    monkeypatch.setattr(selection, "compose_suite", compose_suite)
    monkeypatch.setattr(
        command,
        "paths",
        SimpleNamespace(
            manual_sources=tmp_path / "sources.toml",
            manual_profiles=tmp_path / "manual",
            manual_cache=tmp_path / "cache",
            root=tmp_path,
        ),
    )
    monkeypatch.setattr(command, "ManualSources", SimpleNamespace(from_path=lambda _: object()))
    monkeypatch.setattr(command, "download_manual_assets", download_assets)
    monkeypatch.setattr(command, "compile_manual_artifacts", prepare)

    await command.compile_manuals(suites=["one", "two"])

    assert captured_requirements == [
        ManualRequirement(profile=profile, rule_seed=1),
        ManualRequirement(profile=profile, rule_seed=2),
    ]


def test_explicit_suite_revision_selects_its_frozen_manual_requirement() -> None:
    selected = selection.select_manual_requirements(suites=["multi-self-sync@1"], paths=Paths())

    assert len(selected.requirements) == 1
    assert selected.requirements[0].rule_seed == 1
    assert selected.suites[0].suite_name == "multi-self-sync@1"
