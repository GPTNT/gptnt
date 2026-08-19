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
    sources = ManualSources.from_path(Paths().manual_sources)

    assert sources.official_manual["pt-BR"].pages["WhosOnFirst"] == OfficialPageRange(
        first=9, last=10
    )


def test_ktane_content_source_requires_a_full_commit_sha() -> None:
    with pytest.raises(ValidationError):
        _ = KtaneContentSource(
            repository="https://content.test/repository.git",
            commit="../main",
            catalog=KtaneContentCatalogSource(url="https://content.test/catalog"),
        )
