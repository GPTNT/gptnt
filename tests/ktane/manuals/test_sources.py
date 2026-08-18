from gptnt.common.paths import Paths
from gptnt.ktane.manuals.sources import ManualSources

OFFICIAL_LANGUAGE_CODES = {
    "ar",
    "cs",
    "da",
    "de",
    "en",
    "eo",
    "es",
    "fi",
    "fr",
    "he",
    "hu",
    "it",
    "ja",
    "ko",
    "nb",
    "nl",
    "pl",
    "pt-BR",
    "pt-PT",
    "ro",
    "ru",
    "sv",
    "th",
    "tr",
    "uk",
    "zh-CN",
    "zh-TW",
}


def test_shipped_sources_include_every_official_language() -> None:
    sources = ManualSources.from_path(Paths().manual_sources)

    assert set(sources.official_manual) == OFFICIAL_LANGUAGE_CODES
