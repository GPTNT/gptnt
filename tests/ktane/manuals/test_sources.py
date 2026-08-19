"""Manual source configuration validation."""

import pytest
from pydantic import ValidationError

from gptnt.common.paths import Paths
from gptnt.ktane.manuals.sources import (
    KtaneContentCatalogSource,
    KtaneContentSource,
    ManualSources,
    OfficialPageRange,
)


def test_shipped_sources_parse_an_official_page_range() -> None:
    """Load one nested language and multi-page interval through the shipped TOML schema."""
    sources = ManualSources.from_path(Paths().manual_sources)

    assert sources.official_manual["pt-BR"].pages["WhosOnFirst"] == OfficialPageRange(
        first=9, last=10
    )


def test_ktane_content_source_requires_a_full_commit_sha() -> None:
    """Reject moving revisions and paths where a pinned Git commit is required."""
    with pytest.raises(ValidationError):
        _ = KtaneContentSource(
            repository="https://content.test/repository.git",
            commit="../main",
            catalog=KtaneContentCatalogSource(url="https://content.test/catalog"),
        )
