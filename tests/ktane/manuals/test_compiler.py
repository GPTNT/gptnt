"""Playwright/PyMuPDF manual compilation and artifact caching."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pymupdf
import pytest

from gptnt.ktane.manuals.compiler import ManualCompileError, compile_manual
from gptnt.ktane.manuals.compiler_sources import keypad_assets_root, ktane_content_root
from gptnt.ktane.manuals.resolution import (
    LocalInputIdentity,
    LocalProvenance,
    OfficialManualProvenance,
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
        supports_requested_rule_seed=True,
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
        supports_requested_rule_seed=True,
    )


def _write_pdf(path: Path, texts: list[str]) -> None:
    """Create a US Letter fixture PDF with one identifying text string per page."""
    document = pymupdf.open()
    for text in texts:
        page = document.new_page(width=612, height=792)
        _ = page.insert_text((72, 72), text, fontsize=18)
    document.save(path)
    document.close()


def _write_page(path: Path, *, heading: str, body: str, script: str = "") -> None:
    """Write one executable HTML fixture and its adjacent image dependency."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(_PAGE.format(heading=heading, body=body, script=script), encoding="utf-8")
    _ = path.with_name("fixture.png").write_bytes(_PNG)


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
        (artifact / "pages" / f"{page_number:04d}.txt").read_text(encoding="utf-8")
        for page_number in (1, 2)
    ]
    assert "JS SECOND" in texts[0]
    assert "JS FIRST" in texts[1]
    assert all("print-only" in text and "screen-only" not in text for text in texts)
    assert (artifact / "handbook.pdf").is_file()
    assert (artifact / "pages" / "0001.png").is_file()
    with pymupdf.open(artifact / "handbook.pdf") as handbook:
        assert handbook.page_count == 2
        assert all(handbook.get_page_fonts(page_number) for page_number in range(2))


@pytest.mark.parametrize(
    ("html", "match"),
    [
        (
            _PAGE.format(
                heading="external",
                body="blocked request",
                script="fetch('https://example.invalid/input').catch(() => {});",
            ),
            "non-loopback requests",
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
    """Reject external requests, uncaught scripts, and images that fail to decode."""
    cache_dir = tmp_path / "cache"
    browser_sources(cache_dir)
    source = tmp_path / "manual.html"
    _ = source.write_text(html, encoding="utf-8")
    _ = source.with_name("fixture.png").write_bytes(_PNG)

    with pytest.raises(ManualCompileError, match=match):
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
    with pymupdf.open(artifact / "handbook.pdf") as handbook:
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
    with pytest.raises(ManualCompileError, match="High-resolution Keypad assets"):
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

    first = (artifact / "pages" / "0001.txt").read_text(encoding="utf-8")
    second = (artifact / "pages" / "0002.txt").read_text(encoding="utf-8")
    assert "official page three" in first
    assert "official page one" in second


def test_cache_reuses_invalidates_and_rebuilds(tmp_path: Path) -> None:
    """Reuse valid artifacts and rebuild after input changes or output deletion."""
    source = tmp_path / "official.pdf"
    _write_pdf(source, ["first source version"])
    document = _official_document(source, document_id="Page", first=1, last=1)
    cache_dir = tmp_path / "cache"

    first = compile_manual([document], cache_dir=cache_dir)
    first_pdf_time = (first / "handbook.pdf").stat().st_mtime_ns
    assert compile_manual([document], cache_dir=cache_dir) == first
    assert (first / "handbook.pdf").stat().st_mtime_ns == first_pdf_time

    source.unlink()
    _write_pdf(source, ["second source version"])
    changed = compile_manual([document], cache_dir=cache_dir)
    assert changed != first
    incomplete_page = changed / "pages" / "0001.png"
    incomplete_page.unlink()

    assert compile_manual([document], cache_dir=cache_dir) == changed
    assert incomplete_page.is_file()
