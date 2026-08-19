"""Render resolved HTML and PDF documents into canonical page files."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pymupdf
from bs4 import BeautifulSoup

from gptnt.ktane.manuals.resolution import ResolvedOfficialDocument

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.ktane.manuals.resolution import ResolvedDocument

_CANONICAL_DPI = 144
_HTML_PAGE = pymupdf.paper_rect("a4")
_HTML_CONTENT = _HTML_PAGE + (  # noqa: RUF005 - Rect addition shifts its four coordinates.
    36,
    36,
    -36,
    -36,
)


@dataclass(frozen=True, kw_only=True)
class RenderedPage:
    """Text and PNG path produced for one source-document page."""

    document_page_number: int
    text_path: Path
    image_path: Path


def render_document(
    document: ResolvedDocument, *, output_dir: Path, first_page_number: int
) -> tuple[RenderedPage, ...]:
    """Render one resolved document to ordered UTF-8 text and canonical PNG pages."""
    if isinstance(document, ResolvedOfficialDocument):
        return _extract_pdf_pages(
            document.source_path,
            first=document.page_range.first,
            last=document.page_range.last,
            output_dir=output_dir,
            first_page_number=first_page_number,
        )

    rendered_pdf = output_dir / f"document-{first_page_number:04d}.pdf"
    _render_html_pdf(document.source_path, output_path=rendered_pdf)
    try:
        pages = _extract_pdf_pages(
            rendered_pdf,
            first=1,
            last=None,
            output_dir=output_dir,
            first_page_number=first_page_number,
        )
    except BaseException:
        rendered_pdf.unlink(missing_ok=True)
        raise
    rendered_pdf.unlink()
    return pages


def _render_html_pdf(source_path: Path, *, output_path: Path) -> None:
    """Paginate HTML with PyMuPDF Story and resolve assets beside the source."""
    html = source_path.read_text(encoding="utf-8")
    fragments = _html_page_fragments(html)
    archive = pymupdf.Archive(str(source_path.parent))
    writer = pymupdf.DocumentWriter(output_path)
    try:
        for fragment in fragments:
            _write_story(fragment, archive=archive, writer=writer, source_path=source_path)
    except BaseException:
        writer.close()
        raise
    writer.close()


def _html_page_fragments(html: str) -> tuple[str, ...]:
    """Keep KtaneContent `.page` elements on separate canonical pages."""
    soup = BeautifulSoup(html, "html.parser")
    pages = soup.select(".page")
    if pages:
        head = "" if soup.head is None else str(soup.head)
        return tuple(f"<!doctype html><html>{head}<body>{page}</body></html>" for page in pages)
    return (html,)


def _write_story(
    html: str, *, archive: pymupdf.Archive, writer: pymupdf.DocumentWriter, source_path: Path
) -> None:
    """Flow one HTML fragment onto one or more A4 pages."""
    story = pymupdf.Story(html=html, archive=archive)
    more = True
    while more:
        device = writer.begin_page(_HTML_PAGE)
        more, filled = story.place(_HTML_CONTENT)
        if more and pymupdf.Rect(filled).is_empty:
            raise ValueError(f"HTML content cannot fit on a canonical page: {source_path}")
        story.draw(device)
        writer.end_page()


def _extract_pdf_pages(
    source_path: Path, *, first: int, last: int | None, output_dir: Path, first_page_number: int
) -> tuple[RenderedPage, ...]:
    """Extract an inclusive one-based PDF interval into prompt page files."""
    pages: list[RenderedPage] = []
    with pymupdf.open(source_path) as source:
        final_page = len(source) if last is None else last
        if first > len(source) or final_page > len(source):
            raise ValueError(
                f"PDF page interval {first}-{final_page} exceeds {len(source)} pages in {source_path}"
            )
        for output_offset, source_page_number in enumerate(range(first - 1, final_page)):
            page_number = first_page_number + output_offset
            text_path = output_dir / "text" / f"page-{page_number:04d}.txt"
            image_path = output_dir / "images" / f"page-{page_number:04d}.png"
            text_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.parent.mkdir(parents=True, exist_ok=True)

            page = source[source_page_number]
            text = page.get_text("text")
            if not isinstance(text, str):
                raise TypeError(f"PDF text extraction returned a non-text value for {source_path}")
            text = text.strip()
            _ = text_path.write_text(f"{text}\n" if text else "", encoding="utf-8")
            page.get_pixmap(dpi=_CANONICAL_DPI, alpha=False).save(image_path)
            pages.append(
                RenderedPage(
                    document_page_number=source_page_number + 1,
                    text_path=text_path,
                    image_path=image_path,
                )
            )
    return tuple(pages)
