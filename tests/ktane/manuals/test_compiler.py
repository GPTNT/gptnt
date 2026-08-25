"""Playwright/PyMuPDF manual compilation and artifact caching."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import orjson
import pymupdf
import pytest
from PIL import Image

from gptnt.ktane.manuals.artifacts import compile_manual
from gptnt.ktane.manuals.compiler_sources import (
    KTANE_CONTENT_COMMIT,
    keypad_assets_root,
    ktane_content_root,
)
from gptnt.ktane.manuals.resolution import (
    KtaneContentModuleMetadata,
    KtaneContentProvenance,
    LocalInputIdentity,
    LocalProvenance,
    OfficialManualProvenance,
    ResolvedKtaneContentModule,
    ResolvedLocalDocument,
    ResolvedOfficialDocument,
)
from gptnt.ktane.manuals.sources import OfficialPageRange

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_MERGER = """<!doctype html>
<button type="button">Upload profile</button><input type="file" hidden>
<div class="manuals"></div>
<script>
// Mimic only the upstream profile-upload and ordered-iframe behavior used by the compiler.
const button = document.querySelector('button');
const input = document.querySelector('input');
button.addEventListener('click', () => input.click());
input.addEventListener('change', async () => {
  const profile = JSON.parse(await input.files[0].text());
  button.remove();
  input.remove();
  const modules = (await (await fetch('/json/raw')).json()).KtaneModules
    .filter(module => profile.EnabledList.includes(module.ModuleID))
    .sort((left, right) => left.SortKey.localeCompare(right.SortKey));
  const manuals = document.querySelector('.manuals');
  const contents = document.createElement('div');
  contents.className = 'page';
  contents.textContent = 'Contents';
  manuals.append(contents);
  for (const module of modules) {
    const frame = document.createElement('iframe');
    frame.src = `/HTML/${encodeURIComponent(module.FileName)}.html?merger`;
    manuals.append(frame);
  }
});
</script>
<style>
body { margin: 0; }
iframe { display: block; border: 0; width: 8.5in; height: 11in; }
.manuals > .page { width: 8.5in; height: 11in; }
@media print {
  .manuals > .page, iframe { break-after: page; }
}
</style>
"""

_PAGE = """<!doctype html>
<style>
@font-face {{ font-family: fixture; src: local('Arial'), local('DejaVu Sans'); }}
body {{ margin: 0; font-family: fixture, sans-serif; }}
.page {{ box-sizing: border-box; width: 8.5in; height: 11in; padding: 0.6in; }}
.print-only {{ display: none; }}
@media print {{ .screen-only {{ display: none; }} .print-only {{ display: block; }} }}
</style>
<div class="section"><div class="page">
<h1 id="heading">before-script</h1>
<p class="screen-only">screen-only</p><p class="print-only">print-only</p>
<img src="fixture.png" alt="fixture"><p>{body}</p>
</div></div>
<script>
// Mutating the heading proves the compiler waits for and captures executed page JavaScript.
document.querySelector('#heading').textContent = '{heading}';{script}
</script>
"""

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDAT\x08\xd7c\xf8\xcf"
    b"\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def browser_sources() -> Callable[[Path], None]:
    """Create the merger path expected by the compiler without fetching pinned sources."""

    # The fixture closure writes into the temporary cache selected by each browser test.
    def create(cache_dir: Path) -> None:  # noqa: WPS430
        """Write the synthetic merger into the compiler's expected pinned-source path."""
        merger = ktane_content_root(cache_dir) / "More" / "Manual Merger" / "index.html"
        merger.parent.mkdir(parents=True)
        _ = merger.write_text(_MERGER, encoding="utf-8")

    return create


def _local_document(path: Path, *, document_id: str) -> ResolvedLocalDocument:
    """Resolve one fixture HTML file with provenance matching its current bytes."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return ResolvedLocalDocument(
        document_id=document_id,
        language="en",
        source="local",
        source_path=path,
        provenance=LocalProvenance(inputs=(LocalInputIdentity(path=path.name, sha256=digest),)),
        rule_seed_fragment=None,
    )


def _ktane_content_document(
    cache_dir: Path, *, document_id: str, supports_rule_seed: bool
) -> ResolvedKtaneContentModule:
    """Create one pinned KtaneContent HTML module that reports its URL fragment."""
    root = ktane_content_root(cache_dir)
    source_path = root / "HTML" / f"{document_id}.html"
    _write_page(
        source_path,
        heading=document_id,
        body="module page",
        script=(
            "const applyRuleSeed = () => { "
            "document.body.classList.toggle('ruleseed-active', Boolean(window.location.hash)); "
            "document.querySelector('#heading').textContent = window.location.hash || 'unseeded'; "
            "}; applyRuleSeed(); window.onhashchange = applyRuleSeed;"
        ),
    )
    metadata_path = root / "JSON" / f"{document_id}.json"
    metadata_payload: dict[str, str] = {
        "ModuleID": document_id,
        "Name": document_id,
        "Origin": "Test",
        "SortKey": document_id.upper(),
    }
    if supports_rule_seed:
        metadata_payload["RuleSeedSupport"] = "Supported"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    _ = metadata_path.write_bytes(orjson.dumps(metadata_payload))
    return ResolvedKtaneContentModule(
        document_id=document_id,
        language="en",
        source="ktanecontent",
        source_path=source_path,
        metadata_path=metadata_path,
        metadata=KtaneContentModuleMetadata.model_validate(metadata_payload),
        provenance=KtaneContentProvenance(
            commit=KTANE_CONTENT_COMMIT,
            document=source_path.name,
            metadata_document=metadata_path.name,
        ),
        rule_seed_fragment=7 if supports_rule_seed else None,
    )


def _official_document(
    path: Path, *, document_id: str, first: int, last: int
) -> ResolvedOfficialDocument:
    """Resolve one fixture range from an official-style source PDF."""
    return ResolvedOfficialDocument(
        document_id=document_id,
        language="en",
        source="official",
        source_path=path,
        page_range=OfficialPageRange(first=first, last=last),
        provenance=OfficialManualProvenance(version="fixture", url="https://manual.test/a.pdf"),
        rule_seed_fragment=None,
    )


def _write_pdf(path: Path, texts: list[str]) -> None:
    """Create a US Letter fixture PDF with one identifying text string per page."""
    document = pymupdf.open()
    for text in texts:
        page = document.new_page(width=612, height=792)
        _ = page.insert_text((72, 72), text, fontsize=18)
    document.save(path)
    document.close()


def _write_table_pdf(path: Path, *, rows: list[list[str]], header_x_offset: int = 0) -> None:
    """Create a PDF page with prose around one ruled text table."""
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    _ = page.insert_text((72, 72), "Before table", fontsize=12)
    table = pymupdf.Rect(72, 120, 72 + 100 * len(rows[0]), 120 + 30 * len(rows))
    for row_index in range(len(rows) + 1):
        line_y = table.y0 + 30 * row_index
        _ = page.draw_line((table.x0, line_y), (table.x1, line_y))
    for column_index in range(len(rows[0]) + 1):
        line_x = table.x0 + 100 * column_index
        _ = page.draw_line((line_x, table.y0), (line_x, table.y1))
    for row_index, row in enumerate(rows):
        row_x_offset = 0
        if row_index == 0:
            row_x_offset = header_x_offset
        for column_index, value in enumerate(row):
            _ = page.insert_text(
                (80 + 100 * column_index + row_x_offset, 140 + 30 * row_index), value, fontsize=12
            )
    _ = page.insert_text((72, table.y1 + 30), "After table", fontsize=12)
    document.save(path)
    document.close()


def _write_page(path: Path, *, heading: str, body: str, script: str = "") -> None:
    """Write one executable HTML fixture and its adjacent image dependency."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(_PAGE.format(heading=heading, body=body, script=script), encoding="utf-8")
    _ = path.with_name("fixture.png").write_bytes(_PNG)


def test_compiler_seeds_only_supported_ktane_content_modules(
    tmp_path: Path, browser_sources: Callable[[Path], None]
) -> None:
    """Static KtaneContent pages stay fragment-free beside a seeded module."""
    cache_dir = tmp_path / "cache"
    browser_sources(cache_dir)
    supported = _ktane_content_document(cache_dir, document_id="Seeded", supports_rule_seed=True)
    unsupported = _ktane_content_document(
        cache_dir, document_id="Static", supports_rule_seed=False
    )

    artifact = compile_manual([supported, unsupported], cache_dir=cache_dir, rule_seed=7)

    assert artifact.pages[0][0].startswith("#7")
    assert artifact.pages[1][0].startswith("unseeded")
    assert [artifact_input["rule_seed_fragment"] for artifact_input in artifact.inputs] == [
        7,
        None,
    ]


def test_browser_executes_and_prints_ordered_local_html(
    tmp_path: Path, browser_sources: Callable[[Path], None]
) -> None:
    """Exercise JavaScript, font/image waits, print CSS, PDF text, PNG, and resolver order."""
    cache_dir = tmp_path / "cache"
    browser_sources(cache_dir)
    second = tmp_path / "second" / "manual.html"
    first = tmp_path / "first" / "manual.html"
    _write_page(second, heading="JS SECOND", body="second body")
    _write_page(first, heading="JS FIRST", body="first body")

    artifact = compile_manual(
        [
            _local_document(second, document_id="Second"),
            _local_document(first, document_id="First"),
        ],
        cache_dir=cache_dir,
    )

    texts = [
        (artifact.path / "pages" / f"{page_number:04d}.txt").read_text(encoding="utf-8")
        for page_number in (1, 2)
    ]
    assert "JS SECOND" in texts[0]
    assert "JS FIRST" in texts[1]
    assert all("print-only" in text and "screen-only" not in text for text in texts)
    assert (artifact.path / "handbook.pdf").is_file()
    assert (artifact.path / "pages" / "0001.png").is_file()
    with pymupdf.open(artifact.path / "handbook.pdf") as handbook:
        assert handbook.page_count == 2
        assert all(handbook.get_page_fonts(page_number) for page_number in range(2))


def test_browser_prints_background_image_with_apostrophe_in_url(
    tmp_path: Path, browser_sources: Callable[[Path], None]
) -> None:
    """Keep quoted CSS URLs absolute when their filename contains an apostrophe."""
    cache_dir = tmp_path / "cache"
    browser_sources(cache_dir)
    source = tmp_path / "manual.html"
    html = _PAGE.replace(
        "</style>",
        '.background-marker {{ width: 8px; height: 8px; background: url("fixture\'s.png"); }}'
        "</style>",
    ).format(heading="background", body='<div class="background-marker"></div>', script="")
    _ = source.write_text(html, encoding="utf-8")
    _ = source.with_name("fixture.png").write_bytes(_PNG)
    image = Image.new("RGB", (8, 8), color="red")
    image.save(source.with_name("fixture's.png"))

    artifact = compile_manual(
        [_local_document(source, document_id="Background")], cache_dir=cache_dir
    )

    with pymupdf.open(artifact.path / "handbook.pdf") as handbook:
        assert any(image[2:4] == (8, 8) for image in handbook.get_page_images(0))


def test_browser_keeps_module_stylesheets_out_of_other_documents(
    tmp_path: Path, browser_sources: Callable[[Path], None]
) -> None:
    cache_dir = tmp_path / "cache"
    browser_sources(cache_dir)
    first = tmp_path / "first" / "manual.html"
    second = tmp_path / "second" / "manual.html"
    first_html = _PAGE.replace("</style>", ".first-marker {{ display: block; }}</style>").format(
        heading="FIRST", body='<p class="first-marker">FIRST MARKER</p>', script=""
    )
    second_html = _PAGE.replace("</style>", ".first-marker {{ display: none; }}</style>").format(
        heading="SECOND", body="second body", script=""
    )
    for source, html in ((first, first_html), (second, second_html)):
        source.parent.mkdir(parents=True)
        _ = source.write_text(html, encoding="utf-8")
        _ = source.with_name("fixture.png").write_bytes(_PNG)

    artifact = compile_manual(
        [
            _local_document(first, document_id="First"),
            _local_document(second, document_id="Second"),
        ],
        cache_dir=cache_dir,
    )

    assert "FIRST MARKER" in artifact.pages[0][0]


@pytest.mark.parametrize(
    ("html", "match"),
    [
        (
            _PAGE.format(
                heading="external",
                body="blocked request",
                script="fetch('https://example.invalid/input').catch(() => {});",
            ),
            "outside the compiler origin",
        ),
        (
            _PAGE.format(
                heading="loopback",
                body="blocked loopback service",
                script="fetch('http://127.0.0.1:9/input').catch(() => {});",
            ),
            "outside the compiler origin",
        ),
        (
            _PAGE.format(
                heading="error",
                body="page error",
                script="setTimeout(() => { throw new Error('fixture boom'); }, 0);",
            ),
            "JavaScript errors",
        ),
        (
            _PAGE.replace('src="fixture.png"', 'src="missing.png"').format(
                heading="broken", body="broken image", script=""
            ),
            "broken images",
        ),
    ],
)
def test_browser_rejects_unsafe_or_incomplete_pages(
    tmp_path: Path, browser_sources: Callable[[Path], None], html: str, match: str
) -> None:
    """Reject other origins, uncaught scripts, and images that fail to decode."""
    cache_dir = tmp_path / "cache"
    browser_sources(cache_dir)
    source = tmp_path / "manual.html"
    _ = source.write_text(html, encoding="utf-8")
    _ = source.with_name("fixture.png").write_bytes(_PNG)

    with pytest.raises(RuntimeError, match=match):
        _ = compile_manual([_local_document(source, document_id="Unsafe")], cache_dir=cache_dir)


def test_keypad_uses_required_high_resolution_asset(
    tmp_path: Path, browser_sources: Callable[[Path], None]
) -> None:
    """Replace known Keypad images and reject references to absent committed assets."""
    source = tmp_path / "manual.html"
    _ = source.write_text(
        _PAGE.replace(
            'src="fixture.png"',
            'class="keypad-symbol-image" src="/HTML/img/Keypad/1-copyright.png"',
        ).format(heading="Keypad", body="high resolution symbol", script=""),
        encoding="utf-8",
    )
    resolved = _local_document(source, document_id="Keypad")

    cache_dir = tmp_path / "complete"
    browser_sources(cache_dir)
    committed_assets = sorted(keypad_assets_root().glob("*.png"))
    assert len(committed_assets) == 35
    assert all(
        (pixmap := pymupdf.Pixmap(asset)).width == 256 and pixmap.height == 256
        for asset in committed_assets
    )
    artifact = compile_manual([resolved], cache_dir=cache_dir)
    with pymupdf.open(artifact.path / "handbook.pdf") as handbook:
        images = handbook.get_page_images(0, full=True)
    assert any(image[2:4] == (256, 256) for image in images)

    missing_source = tmp_path / "missing.html"
    _ = missing_source.write_text(
        _PAGE.replace(
            'src="fixture.png"',
            'class="keypad-symbol-image" src="/HTML/img/Keypad/not-committed.png"',
        ).format(heading="Keypad", body="missing symbol", script=""),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="High-resolution Keypad assets"):
        _ = compile_manual(
            [_local_document(missing_source, document_id="MissingKeypad")], cache_dir=cache_dir
        )


def test_official_page_ranges_follow_resolver_order(tmp_path: Path) -> None:
    """Insert selected physical PDF pages in resolver order rather than source order."""
    source = tmp_path / "official.pdf"
    _write_pdf(source, ["official page one", "official page two", "official page three"])
    documents = [
        _official_document(source, document_id="Third", first=3, last=3),
        _official_document(source, document_id="First", first=1, last=1),
    ]

    artifact = compile_manual(documents, cache_dir=tmp_path / "cache")

    first, second = (text for text, _image in artifact.pages)
    assert "official page three" in first
    assert "official page one" in second


def test_text_extraction_writes_dense_table_rows_in_reading_order(tmp_path: Path) -> None:
    source = tmp_path / "table.pdf"
    _write_table_pdf(
        source,
        rows=[
            ["Flash", "No strikes", "1 strike"],
            ["Red", "Blue", "Yellow"],
            ["Blue", "Red", "Green"],
        ],
    )

    artifact = compile_manual(
        [_official_document(source, document_id="Table", first=1, last=1)],
        cache_dir=tmp_path / "cache",
    )

    assert artifact.pages[0][0] == (
        "Before table\n"
        "Flash | No strikes | 1 strike\n"
        "Red | Blue | Yellow\n"
        "Blue | Red | Green\n"
        "After table\n"
    )


def test_text_extraction_keeps_sparse_grids_as_prose(tmp_path: Path) -> None:
    source = tmp_path / "sparse-grid.pdf"
    _write_table_pdf(source, rows=[["YES", ""], ["", ""], ["", ""]])

    artifact = compile_manual(
        [_official_document(source, document_id="Grid", first=1, last=1)],
        cache_dir=tmp_path / "cache",
    )

    assert "YES" in artifact.pages[0][0]
    assert "|" not in artifact.pages[0][0]


def test_text_extraction_does_not_duplicate_table_text_at_a_border(tmp_path: Path) -> None:
    source = tmp_path / "border-table.pdf"
    _write_table_pdf(
        source,
        rows=[["Flash", "No strikes"], ["Red", "Blue"], ["Blue", "Red"]],
        header_x_offset=-10,
    )

    artifact = compile_manual(
        [_official_document(source, document_id="Border", first=1, last=1)],
        cache_dir=tmp_path / "cache",
    )

    assert artifact.pages[0][0].count("Flash") == 1


def test_cache_reuses_invalidates_and_rebuilds(tmp_path: Path) -> None:
    """Reuse valid artifacts and rebuild after input changes or output deletion."""
    source = tmp_path / "official.pdf"
    _write_pdf(source, ["first source version"])
    document = _official_document(source, document_id="Page", first=1, last=1)
    cache_dir = tmp_path / "cache"

    first = compile_manual([document], cache_dir=cache_dir)
    first_pdf_time = (first.path / "handbook.pdf").stat().st_mtime_ns
    assert compile_manual([document], cache_dir=cache_dir) == first
    assert (first.path / "handbook.pdf").stat().st_mtime_ns == first_pdf_time

    source.unlink()
    _write_pdf(source, ["second source version"])
    changed = compile_manual([document], cache_dir=cache_dir)
    assert changed != first
    incomplete_page = changed.path / "pages" / "0001.png"
    incomplete_page.unlink()

    assert compile_manual([document], cache_dir=cache_dir) == changed
    assert incomplete_page.is_file()


def test_cache_separates_artifacts_by_rule_seed(tmp_path: Path) -> None:
    """The manual cache cannot reuse one profile's artifact for a different rule set."""
    source = tmp_path / "official.pdf"
    _write_pdf(source, ["one page"])
    document = _official_document(source, document_id="Page", first=1, last=1)

    first = compile_manual([document], cache_dir=tmp_path / "cache", rule_seed=1)
    second = compile_manual([document], cache_dir=tmp_path / "cache", rule_seed=2)

    assert first.path != second.path
    assert (first.rule_seed, second.rule_seed) == (1, 2)
