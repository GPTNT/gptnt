"""Canonical manual compilation, cache validation, and image variants."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pymupdf
import pytest
from PIL import Image

from gptnt.ktane.manuals import _compile
from gptnt.ktane.manuals._artifact import ArtifactManifest, RendererIdentity
from gptnt.ktane.manuals.compiler import compile_manual, prepare_manual_variant
from gptnt.ktane.manuals.profile import (
    KtaneContentDocument,
    LocalDocument,
    ManualProfile,
    OfficialDocument,
)
from gptnt.ktane.manuals.resolution import (
    KtaneContentModuleMetadata,
    KtaneContentProvenance,
    LocalInputIdentity,
    LocalProvenance,
    OfficialManualProvenance,
    ResolvedDocument,
    ResolvedKtaneContentModule,
    ResolvedLocalDocument,
    ResolvedOfficialDocument,
)
from gptnt.ktane.manuals.sources import OfficialPageRange

if TYPE_CHECKING:
    from pathlib import Path

_COMMIT = "1" * 40
_PAGE_STYLE = """
    @page { size: 100mm 120mm; margin: 8mm; }
    body { font-family: sans-serif; }
    .page { break-after: page; }
    .page:last-child { break-after: auto; }
"""


def _write(path: Path, content: str) -> None:
    """Write one UTF-8 source fixture and create its parent directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _local_document(path: Path, *, document_id: str = "Local") -> ResolvedLocalDocument:
    return ResolvedLocalDocument(
        document_id=document_id,
        language="en",
        source="local",
        source_path=path,
        provenance=LocalProvenance(
            inputs=(LocalInputIdentity(path=path.name, sha256=_sha256(path)),)
        ),
        supports_requested_rule_seed=True,
    )


def _simple_build(tmp_path: Path) -> tuple[ManualProfile, tuple[ResolvedDocument, ...]]:
    source_path = tmp_path / "local.html"
    _write(source_path, f"<style>{_PAGE_STYLE}</style><div class='page'>Local text</div>")
    profile = ManualProfile(
        include_frontmatter=False,
        documents=(LocalDocument(source="local", path=source_path, language="en", id="Local"),),
    )
    return profile, (_local_document(source_path),)


def _write_pdf(path: Path) -> None:
    """Create a two-page PDF whose second page is selected by the resolved input."""
    with pymupdf.open() as document:
        first = document.new_page()
        _ = first.insert_text((40, 60), "Unused official page")
        second = document.new_page()
        _ = second.insert_text((40, 60), "Official selected text")
        document.save(path)


def test_compiles_resolved_documents_to_ordered_text_and_png_pages(tmp_path: Path) -> None:
    """Preserve document and page order across KtaneContent HTML, local HTML, and PDF."""
    ktane_path = tmp_path / "ktane" / "HTML" / "Wires.html"
    metadata_path = tmp_path / "ktane" / "JSON" / "Wires.json"
    _write(
        ktane_path,
        f"""
        <style>{_PAGE_STYLE}</style>
        <div class="section"><div class="page">
          <img src="wire.svg"><h1>On the Subject of Wires</h1><p>Cut one wire.</p>
        </div></div>
        """,
    )
    _write(
        ktane_path.with_name("wire.svg"),
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10"><path d="M0 5h20"/></svg>',
    )
    _write(metadata_path, '{"ModuleID":"Wires"}')

    local_path = tmp_path / "local.html"
    _write(
        local_path,
        f"""
        <style>{_PAGE_STYLE}</style>
        <div class="page"><h1>Local page one</h1></div>
        <div class="page"><h1>Local page two</h1></div>
        """,
    )
    pdf_path = tmp_path / "manual.pdf"
    _write_pdf(pdf_path)

    profile = ManualProfile(
        include_frontmatter=False,
        documents=(
            KtaneContentDocument(source="ktanecontent", id="Wires", language="en"),
            LocalDocument(source="local", path=local_path, language="en", id="Local"),
            OfficialDocument(source="official", id="Official", language="en"),
        ),
    )
    resolved: tuple[ResolvedDocument, ...] = (
        ResolvedKtaneContentModule(
            document_id="Wires",
            language="en",
            source="ktanecontent",
            source_path=ktane_path,
            metadata_path=metadata_path,
            metadata=KtaneContentModuleMetadata(
                ModuleID="Wires", Name="Wires", Origin="Vanilla", SortKey="WIRES"
            ),
            provenance=KtaneContentProvenance(
                commit=_COMMIT, document="Wires.html", metadata_document="Wires.json"
            ),
            supports_requested_rule_seed=True,
        ),
        _local_document(local_path),
        ResolvedOfficialDocument(
            document_id="Official",
            language="en",
            source="official",
            source_path=pdf_path,
            page_range=OfficialPageRange(first=2, last=2),
            provenance=OfficialManualProvenance(version="1", url="https://manual.test/manual.pdf"),
            supports_requested_rule_seed=True,
        ),
    )

    artifact = compile_manual(profile, resolved, cache_dir=tmp_path / "cache")
    manifest = ArtifactManifest.model_validate_json((artifact.path / "manifest.json").read_bytes())

    assert [page.document_id for page in artifact.pages] == ["Wires", "Local", "Local", "Official"]
    assert [page.document_page_number for page in artifact.pages] == [1, 1, 2, 2]
    assert [page.document_id for page in manifest.pages] == ["Wires", "Local", "Local", "Official"]
    page_text = [page.text_path.read_text(encoding="utf-8") for page in artifact.pages]
    assert "Cut one wire" in page_text[0]
    assert "Local page one" in page_text[1]
    assert "Local page two" in page_text[2]
    assert "Official selected text" in page_text[3]
    for page in artifact.pages:
        with Image.open(page.image_path, formats=("PNG",)) as image:
            image.verify()


@pytest.mark.parametrize(
    "change",
    [
        "profile",
        "source_content",
        "source_pin",
        "language",
        "rule_seed",
        "compiler_schema",
        "renderer",
    ],
)
def test_canonical_cache_policy_includes_every_content_input(tmp_path: Path, change: str) -> None:
    """Reuse identical identity inputs and change the digest for each canonical policy input."""
    profile, documents = _simple_build(tmp_path)
    renderer = _compile.renderer_identity()
    resolved_inputs = _compile.resolved_input_manifests(documents)
    compiler_schema = "gptnt.manual.v1"
    rule_seed = 1
    baseline = _compile.canonical_digest(
        profile=profile.model_dump(mode="json"),
        compiler_schema=compiler_schema,
        rule_seed=rule_seed,
        renderer=renderer,
        resolved_inputs=resolved_inputs,
    )
    assert baseline == _compile.canonical_digest(
        profile=profile.model_dump(mode="json"),
        compiler_schema=compiler_schema,
        rule_seed=rule_seed,
        renderer=renderer,
        resolved_inputs=resolved_inputs,
    )

    if change == "profile":
        profile = profile.model_copy(
            update={
                "documents": (
                    LocalDocument(
                        source="local", path=tmp_path / "other.html", language="en", id="Other"
                    ),
                )
            }
        )
    elif change == "source_content":
        _write(documents[0].source_path, f"<style>{_PAGE_STYLE}</style><p>Changed</p>")
        resolved_inputs = _compile.resolved_input_manifests(documents)
    elif change == "source_pin":
        resolved_inputs = (
            resolved_inputs[0].model_copy(update={"provenance": {"commit": "2" * 40}}),
        )
    elif change == "language":
        resolved_inputs = (resolved_inputs[0].model_copy(update={"language": "fr"}),)
    elif change == "rule_seed":
        rule_seed = 2
    elif change == "compiler_schema":
        compiler_schema = "gptnt.manual.v2"
    else:
        renderer = RendererIdentity(
            html="beautifulsoup:next+pymupdf-story:next", pages=renderer.pages
        )

    changed = _compile.canonical_digest(
        profile=profile.model_dump(mode="json"),
        compiler_schema=compiler_schema,
        rule_seed=rule_seed,
        renderer=renderer,
        resolved_inputs=resolved_inputs,
    )
    assert changed != baseline


def test_rebuilds_corrupt_artifacts_and_coordinates_concurrent_builds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile, documents = _simple_build(tmp_path)
    cache_dir = tmp_path / "cache"
    initial = compile_manual(profile, documents, cache_dir=cache_dir)
    manifest_mtime = (initial.path / "manifest.json").stat().st_mtime_ns

    reused = compile_manual(profile, documents, cache_dir=cache_dir)

    assert reused == initial
    assert (reused.path / "manifest.json").stat().st_mtime_ns == manifest_mtime
    _ = (initial.path / "manifest.json").write_text("{", encoding="utf-8")

    rebuilt = compile_manual(profile, documents, cache_dir=cache_dir)
    _ = ArtifactManifest.model_validate_json((rebuilt.path / "manifest.json").read_bytes())
    rebuilt.pages[0].image_path.unlink()

    counted_build = Mock(wraps=_compile._build_manifest)
    monkeypatch.setattr(_compile, "_build_manifest", counted_build)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(compile_manual, profile, documents, cache_dir=cache_dir)
            for _ in range(2)
        ]
    concurrent = [future.result() for future in futures]

    assert counted_build.call_count == 1
    assert concurrent[0] == concurrent[1]
    assert concurrent[0].pages[0].image_path.is_file()
    _ = ArtifactManifest.model_validate_json((concurrent[0].path / "manifest.json").read_bytes())
    assert not list((cache_dir / "compiled").glob(f".{rebuilt.digest}.tmp-*"))
    assert not list((cache_dir / "compiled").glob(f".{rebuilt.digest}.stale-*"))


def test_dimension_variants_reuse_canonical_text_and_their_own_cache(tmp_path: Path) -> None:
    profile, documents = _simple_build(tmp_path)
    canonical = compile_manual(profile, documents, cache_dir=tmp_path / "cache")
    text_before = [(page.text_path, page.text_path.read_bytes()) for page in canonical.pages]

    small = prepare_manual_variant(canonical, width=64, height=48)
    small_manifest_mtime = (small.path / "manifest.json").stat().st_mtime_ns
    large = prepare_manual_variant(canonical, width=96, height=72)
    small_again = prepare_manual_variant(canonical, width=64, height=48)

    assert small_again == small
    assert small.path != large.path
    assert (small.path / "manifest.json").stat().st_mtime_ns == small_manifest_mtime
    assert [(path, path.read_bytes()) for path, _ in text_before] == text_before
    assert not list((canonical.path / "variants").rglob("*.txt"))
    for path in small.image_paths:
        with Image.open(path, formats=("PNG",)) as image:
            assert image.size == (64, 48)
    for path in large.image_paths:
        with Image.open(path, formats=("PNG",)) as image:
            assert image.size == (96, 72)
