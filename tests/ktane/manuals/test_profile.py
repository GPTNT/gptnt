"""Manual profile configuration validation."""

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
    """Load every concrete profile through the model used by configuration composition."""
    for config in Paths().manual_profiles.glob("*.yaml"):
        if config.name.startswith("_"):
            continue
        _ = ManualProfile.model_validate(yaml.safe_load(config.read_text()))


@parametrize_with_cases("document_config,expected_type", cases=DocumentConfigCases)
def test_profile_deserializes_each_document_variant(
    document_config: dict[str, object], expected_type: type[Document]
) -> None:
    """Use the source discriminator to construct each supported document type."""
    profile = ManualProfile.model_validate(
        {"include_frontmatter": False, "documents": [document_config]}
    )

    assert isinstance(profile.documents[0], expected_type)


@pytest.mark.parametrize("document", ["HTML/Wires.html", r"HTML\Wires.html"])
def test_document_override_must_be_a_bare_filename(document: str) -> None:
    """Prevent an HTML override from selecting a path outside KtaneContent's HTML directory."""
    with pytest.raises(ValidationError):
        _ = KtaneContentDocument(
            source="ktanecontent", id="Wires", language="en", document=document
        )


def test_local_document_rejects_a_non_html_path() -> None:
    """Restrict local manual inputs to HTML documents that dependency discovery can inspect."""
    with pytest.raises(ValidationError, match=r"must be an \.html file"):
        _ = LocalDocument(source="local", path=Path("my/notes/Wires.pdf"), language="en")


def test_profile_requires_at_least_one_document() -> None:
    """Ensure every profile contributes a body document after optional frontmatter."""
    with pytest.raises(ValidationError):
        _ = ManualProfile(include_frontmatter=False, documents=())
