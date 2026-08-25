"""Manual source configuration validation."""

from gptnt.common.paths import Paths
from gptnt.ktane.manuals.sources import ManualSources, OfficialPageRange


def test_shipped_sources_parse_an_official_page_range() -> None:
    """Load one nested language and multi-page interval through the provided TOML schema."""
    sources = ManualSources.from_path(Paths().manual_sources)

    assert sources.official_manual["pt-BR"].pages["WhosOnFirst"] == OfficialPageRange(
        first=9, last=10
    )
