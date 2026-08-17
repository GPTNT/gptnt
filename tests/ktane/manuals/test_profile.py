"""Manual profile parsing, and the resolve/download behaviour it is meant to drive.

The `test_resolve_*` and `test_download_*` cases are executable specifications for code that does
not exist yet. Each raises `NotImplementedError` and is marked `xfail(strict=True)`, so the suite
stays green while the intended behaviour is recorded. When the behaviour is implemented, delete the
`raise` and the marker together.
"""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from gptnt.ktane.manuals.profile import (
    KtaneContentAppendix,
    KtaneContentDocument,
    LocalDocument,
    ManualProfile,
    OfficialDocument,
)

_CONFIGS = Path(__file__).parents[3].joinpath("configs", "manual")


# --- profiles for each document type -----------------------------------------------------------


def _ktanecontent_module() -> KtaneContentDocument:
    return KtaneContentDocument(source="ktanecontent", id="Wires", language="en")


def _official_module() -> OfficialDocument:
    return OfficialDocument(source="official", id="Wires", language="fr")


def _appendix() -> KtaneContentAppendix:
    return KtaneContentAppendix(
        source="ktanecontent", language="en", document="Appendix SQUARE.html"
    )


def _local_document() -> LocalDocument:
    return LocalDocument(
        source="local", path=Path("my/notes/Wires.html"), language="en", id="Wires"
    )


# --- profile parsing ---------------------------------------------------------------------------


def test_every_shipped_config_parses() -> None:
    for config in _CONFIGS.glob("*.yaml"):
        if config.name.startswith("_"):
            continue
        _ = ManualProfile.model_validate(yaml.safe_load(config.read_text()))


def test_source_discriminates_the_document_union() -> None:
    profile = ManualProfile(
        include_frontmatter=False,
        documents=(_ktanecontent_module(), _official_module(), _appendix(), _local_document()),
    )

    assert [type(document) for document in profile.documents] == [
        KtaneContentDocument,
        OfficialDocument,
        KtaneContentAppendix,
        LocalDocument,
    ]


def test_ktanecontent_document_takes_an_optional_page_override() -> None:
    document = KtaneContentDocument(
        source="ktanecontent", id="Wires", language="en", document="Wires optimized (Timwi).html"
    )

    assert document.document == "Wires optimized (Timwi).html"


def test_document_override_must_be_a_bare_filename() -> None:
    with pytest.raises(ValidationError):
        _ = KtaneContentDocument(
            source="ktanecontent", id="Wires", language="en", document="HTML/Wires.html"
        )


def test_local_document_rejects_a_non_html_path() -> None:
    with pytest.raises(ValidationError, match=r"must be an \.html file"):
        _ = LocalDocument(source="local", path=Path("my/notes/Wires.pdf"), language="en")


def test_profile_requires_at_least_one_document() -> None:
    with pytest.raises(ValidationError):
        _ = ManualProfile(include_frontmatter=False, documents=())


# --- resolve: executable specification (not implemented) ---------------------------------------


@pytest.mark.xfail(raises=NotImplementedError, strict=True, reason="resolve() not implemented yet")
def test_resolve_raises_when_the_source_lacks_the_document() -> None:
    # A French vanilla page does not exist in KtaneContent; resolving this valid-but-unsatisfiable
    # document must raise a clear error rather than silently substituting or skipping it.
    _document = KtaneContentDocument(source="ktanecontent", id="Wires", language="fr")
    raise NotImplementedError("resolve() must raise when a source has no page for a document")


@pytest.mark.xfail(raises=NotImplementedError, strict=True, reason="resolve() not implemented yet")
def test_resolve_reads_ktanecontent_metadata_for_a_module() -> None:
    # name, sort_key, origin and rule-seed support come from KtaneContent's per-module JSON, not
    # from the profile.
    raise NotImplementedError("resolve() must fill ManualPage metadata from KtaneContent JSON")


@pytest.mark.xfail(raises=NotImplementedError, strict=True, reason="resolve() not implemented yet")
def test_resolve_locates_an_official_page_by_module_id_and_language() -> None:
    # An official document names a module id; resolve finds its page(s) in the official PDF for the
    # requested language via a per-language module -> page map.
    raise NotImplementedError("resolve() must map an official module id to PDF pages by language")


# --- download: executable specification (not implemented) --------------------------------------


@pytest.mark.xfail(
    raises=NotImplementedError, strict=True, reason="download() not implemented yet"
)
def test_download_fetches_only_the_documents_the_profiles_need() -> None:
    # download must not clone the whole KtaneContent tree: it fetches only the resolved file set
    # (sparse), plus one official PDF per language actually used.
    raise NotImplementedError("download() must fetch only the resolved document set")
