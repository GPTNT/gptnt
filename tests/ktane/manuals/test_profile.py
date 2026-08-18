"""Manual profile validation and planned document-resolution behaviour."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from pytest_cases import parametrize_with_cases

from gptnt.common.paths import Paths
from gptnt.ktane.manuals.profile import (
    Document,
    KtaneContentAppendix,
    KtaneContentDocument,
    LocalDocument,
    ManualProfile,
    OfficialDocument,
)


class DocumentConfigCases:
    """Serialized configurations for every supported manual document variant."""

    def case_ktanecontent_module(self) -> tuple[dict[str, object], type[Document]]:
        return ({"source": "ktanecontent", "id": "Wires", "language": "en"}, KtaneContentDocument)

    def case_official_module(self) -> tuple[dict[str, object], type[Document]]:
        return ({"source": "official", "id": "Wires", "language": "fr"}, OfficialDocument)

    def case_appendix(self) -> tuple[dict[str, object], type[Document]]:
        return (
            {"source": "ktanecontent", "language": "en", "document": "Appendix SQUARE.html"},
            KtaneContentAppendix,
        )

    def case_local_document(self) -> tuple[dict[str, object], type[Document]]:
        return (
            {"source": "local", "path": "my/notes/Wires.html", "language": "en", "id": "Wires"},
            LocalDocument,
        )


# --- profile parsing ---------------------------------------------------------------------------


def test_every_shipped_config_parses() -> None:
    for config in Paths().manual_profiles.glob("*.yaml"):
        if config.name.startswith("_"):
            continue
        _ = ManualProfile.model_validate(yaml.safe_load(config.read_text()))


@parametrize_with_cases("document_config,expected_type", cases=DocumentConfigCases)
def test_profile_deserializes_each_document_variant(
    document_config: dict[str, object], expected_type: type[Document]
) -> None:
    profile = ManualProfile.model_validate(
        {"include_frontmatter": False, "documents": [document_config]}
    )

    assert isinstance(profile.documents[0], expected_type)


@pytest.mark.parametrize("document", ["HTML/Wires.html", r"HTML\Wires.html"])
def test_document_override_must_be_a_bare_filename(document: str) -> None:
    with pytest.raises(ValidationError):
        _ = KtaneContentDocument(
            source="ktanecontent", id="Wires", language="en", document=document
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
