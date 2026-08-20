"""Ordered manual source resolution and pre-render compatibility policy."""

from pathlib import Path

import orjson
import pytest

from gptnt.ktane.manuals.profile import LocalDocument, ManualProfile
from gptnt.ktane.manuals.resolution import (
    KtaneContentProvenance,
    LocalProvenance,
    OfficialManualProvenance,
    ResolvedKtaneContentAppendix,
    ResolvedKtaneContentModule,
    ResolvedLocalDocument,
    ResolvedOfficialDocument,
)
from gptnt.ktane.manuals.resolve import ManualResolutionError, resolve_manual_profile
from gptnt.ktane.manuals.sources import (
    KtaneContentCatalogSource,
    KtaneContentSource,
    ManualSources,
    OfficialManualSource,
    OfficialPageRange,
)

COMMIT = "1" * 40


def _write(path: Path, content: str | bytes) -> None:
    """Materialize one source-cache or local-dependency fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        _ = path.write_bytes(content)
    else:
        _ = path.write_text(content, encoding="utf-8")


def _sources(*, frontmatter: tuple[LocalDocument, ...] = ()) -> ManualSources:
    """Build the smallest source configuration that covers every resolver branch."""
    return ManualSources(
        ktane_content=KtaneContentSource(
            repository="https://content.test/repository.git",
            commit=COMMIT,
            catalog=KtaneContentCatalogSource(url="https://content.test/catalog"),
        ),
        frontmatter=frontmatter,
        official_manual={
            "en": OfficialManualSource(
                version="1",
                url="https://manual.test/en.pdf",
                pages={"BigButton": OfficialPageRange(first=6, last=6)},
            )
        },
    )


def _cache_ktane_content(cache_dir: Path) -> None:
    """Create the catalog, HTML, appendix, and JSON files expected from the downloader."""
    catalog = {"KtaneModules": [{"ModuleID": "Wires", "Name": "Wires"}]}
    _write(cache_dir / "sources" / "ktanecontent" / "catalog" / "raw.json", orjson.dumps(catalog))
    revision = cache_dir / "sources" / "ktanecontent" / COMMIT
    _write(revision / "HTML" / "Wires.html", "<main>Cut a wire.</main>")
    _write(revision / "HTML" / "Appendix SQUARE.html", "<main>Appendix.</main>")
    _write(
        revision / "JSON" / "Wires.json",
        orjson.dumps(
            {
                "ModuleID": "Wires",
                "Name": "Wires",
                "Origin": "Vanilla",
                "SortKey": "WIRES",
                "RuleSeedSupport": "Supported",
            }
        ),
    )


def _profile(*documents: object, include_frontmatter: bool = False) -> ManualProfile:
    """Parse serialized document variants through the public profile model."""
    return ManualProfile.model_validate(
        {"include_frontmatter": include_frontmatter, "documents": list(documents)}
    )


def test_resolves_mixed_sources_in_profile_order_with_provenance(tmp_path: Path) -> None:
    """Preserve profile order while selecting each source type and its provenance.

    The local HTML references CSS that references an image. The resulting identity must therefore
    include the complete two-level dependency graph, not only the configured HTML file.
    """
    cache_dir = tmp_path / "cache"
    # Remote inputs must occupy the cache paths produced by the downloader.
    _cache_ktane_content(cache_dir)
    _write(cache_dir / "sources" / "official" / "en" / "1" / "manual.pdf", b"PDF")
    # Local inputs remain under the configured root and may reference one another recursively.
    _write(
        tmp_path / "local" / "notes.html",
        '<link rel="stylesheet" href="style.css"><main>Notes.</main>',
    )
    _write(tmp_path / "local" / "style.css", "body { background: url(image.svg); }")
    _write(tmp_path / "local" / "image.svg", "<svg></svg>")
    profile = _profile(
        {"source": "ktanecontent", "id": "Wires", "language": "en"},
        {"source": "ktanecontent", "document": "Appendix SQUARE.html", "language": "en"},
        {"source": "official", "id": "BigButton", "language": "en"},
        {"source": "local", "id": "Notes", "path": "local/notes.html", "language": "en"},
    )

    resolved = resolve_manual_profile(
        profile,
        sources=_sources(),
        cache_dir=cache_dir,
        root_dir=tmp_path,
        language="en",
        rule_seed=1,
    )

    assert [document.document_id for document in resolved] == [
        "Wires",
        "Appendix SQUARE.html",
        "BigButton",
        "Notes",
    ]
    module, appendix, official, local = resolved
    assert isinstance(module, ResolvedKtaneContentModule)
    assert isinstance(appendix, ResolvedKtaneContentAppendix)
    assert isinstance(official, ResolvedOfficialDocument)
    assert isinstance(local, ResolvedLocalDocument)
    assert module.provenance == KtaneContentProvenance(
        commit=COMMIT, document="Wires.html", metadata_document="Wires.json"
    )
    assert module.metadata.rule_seed_support == "Supported"
    assert appendix.provenance == KtaneContentProvenance(
        commit=COMMIT, document="Appendix SQUARE.html"
    )
    assert official.provenance == OfficialManualProvenance(
        version="1", url="https://manual.test/en.pdf"
    )
    assert (official.page_range.first, official.page_range.last) == (6, 6)
    assert isinstance(local.provenance, LocalProvenance)
    assert [(source.path, source.sha256) for source in local.provenance.inputs] == [
        ("local/image.svg", "b12e0d83ce2357d80b89c57694814d0a3abdaf8c40724f2049af8b7f01b7812b"),
        ("local/notes.html", "294f1c2bb7cc0e5603b182f915141e5b5c4a486879abc9f31faef0206d6e3b0e"),
        ("local/style.css", "0672760d4259787e46e8a95a612f4879b568104efdab70090cc552f0220fd2d7"),
    ]
    assert all(document.supports_requested_rule_seed for document in resolved)


@pytest.mark.parametrize(
    ("policy", "match"),
    [
        ("absent_document", r"documents\[0\].*document 'Missing\.html'.*missing"),
        ("missing_page_map", r"documents\[0\].*no page map for 'Missing'"),
        ("unsupported_rule_seed", r"documents\[0\].*rule seed 2 is unsupported"),
        ("incompatible_language", r"documents\[0\].*language 'fr'.*language 'en'"),
        ("missing_local_dependency", r"documents\[0\].*missing\.css.*is missing"),
        ("escaping_local_dependency", r"documents\[0\].*escapes the configured source root"),
    ],
)
def test_resolution_policy_reports_the_profile_entry(
    tmp_path: Path, policy: str, match: str
) -> None:
    """Name the responsible profile entry for each unsupported pre-render condition.

    Each parameter selects a separate resolver branch and supplies only the files needed to reach
    that branch. The assertions target GPTNT's error context rather than dependency error text.
    """
    cache_dir = tmp_path / "cache"
    _cache_ktane_content(cache_dir)
    sources = _sources()
    language = "en"
    rule_seed = 1
    if policy == "absent_document":
        profile = _profile(
            {"source": "ktanecontent", "id": "Wires", "language": "en", "document": "Missing.html"}
        )
    elif policy == "missing_page_map":
        profile = _profile({"source": "official", "id": "Missing", "language": "en"})
    elif policy == "unsupported_rule_seed":
        _write(tmp_path / "local.html", "local")
        profile = _profile({"source": "local", "path": "local.html", "language": "en"})
        rule_seed = 2
    elif policy == "incompatible_language":
        _write(tmp_path / "local.html", "local")
        profile = _profile({"source": "local", "path": "local.html", "language": "fr"})
    elif policy == "missing_local_dependency":
        _write(tmp_path / "local.html", '<link rel="stylesheet" href="missing.css">')
        profile = _profile({"source": "local", "path": "local.html", "language": "en"})
    else:
        _write(tmp_path / "local.html", '<link rel="stylesheet" href="/%2e%2e/outside.css">')
        profile = _profile({"source": "local", "path": "local.html", "language": "en"})

    with pytest.raises(ManualResolutionError, match=match):
        _ = resolve_manual_profile(
            profile,
            sources=sources,
            cache_dir=cache_dir,
            root_dir=tmp_path,
            language=language,
            rule_seed=rule_seed,
        )


def test_frontmatter_is_inserted_only_when_enabled(tmp_path: Path) -> None:
    """Prepend configured frontmatter without changing the profile document order."""
    _write(tmp_path / "frontmatter.html", "Frontmatter")
    _write(tmp_path / "body.html", "Body")
    frontmatter = LocalDocument(source="local", path=Path("frontmatter.html"), language="en")
    sources = _sources(frontmatter=(frontmatter,))
    document = {"source": "local", "path": "body.html", "language": "en"}

    enabled = resolve_manual_profile(
        _profile(document, include_frontmatter=True),
        sources=sources,
        cache_dir=tmp_path / "cache",
        root_dir=tmp_path,
        language="en",
        rule_seed=1,
    )
    disabled = resolve_manual_profile(
        _profile(document),
        sources=sources,
        cache_dir=tmp_path / "cache",
        root_dir=tmp_path,
        language="en",
        rule_seed=1,
    )

    assert [document.source_path.name for document in enabled] == ["frontmatter.html", "body.html"]
    assert [document.source_path.name for document in disabled] == ["body.html"]
