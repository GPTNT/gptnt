from __future__ import annotations

import contextlib
import hashlib
import shutil
from typing import TYPE_CHECKING, Any

import pymupdf

from gptnt.ktane.manuals import _browser
from gptnt.ktane.manuals.compiler_sources import (
    KTANE_CONTENT_COMMIT,
    keypad_assets_root,
    ktane_content_root,
)
from gptnt.ktane.manuals.resolution import (
    ResolvedDocument,
    ResolvedKtaneContentAppendix,
    ResolvedKtaneContentModule,
    ResolvedOfficialDocument,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


def input_identity(document: ResolvedDocument) -> dict[str, Any]:
    """Describe one resolved input with every value that can affect rendered output."""
    with document.source_path.open("rb") as source_file:
        document_sha256 = hashlib.file_digest(source_file, "sha256").hexdigest()
    # These fields identify all document variants before source-specific provenance is added.
    common: dict[str, Any] = {
        "source": document.source,
        "id": document.document_id,
        "language": document.language,
    }
    # Modules depend on both their HTML and catalog metadata used by the upstream merger.
    if isinstance(document, ResolvedKtaneContentModule):
        if document.provenance.commit != KTANE_CONTENT_COMMIT:
            raise RuntimeError(
                "KtaneContent documents must use the compiler's pinned Manual Merger commit "
                f"{KTANE_CONTENT_COMMIT}; found {document.provenance.commit}"
            )
        with document.metadata_path.open("rb") as metadata:
            metadata_sha256 = hashlib.file_digest(metadata, "sha256").hexdigest()
        return {
            **common,
            "commit": document.provenance.commit,
            "document": document.provenance.document,
            "document_sha256": document_sha256,
            "metadata_document": document.provenance.metadata_document,
            "metadata_sha256": metadata_sha256,
        }
    # Appendices have HTML provenance but no module metadata document.
    if isinstance(document, ResolvedKtaneContentAppendix):
        if document.provenance.commit != KTANE_CONTENT_COMMIT:
            raise RuntimeError(
                "KtaneContent documents must use the compiler's pinned Manual Merger commit "
                f"{KTANE_CONTENT_COMMIT}; found {document.provenance.commit}"
            )
        return {
            **common,
            "commit": document.provenance.commit,
            "document": document.provenance.document,
            "document_sha256": document_sha256,
        }
    # Official inputs are selected PDF page ranges rather than HTML documents.
    if isinstance(document, ResolvedOfficialDocument):
        return {
            **common,
            "version": document.provenance.version,
            "url": document.provenance.url,
            "pdf_sha256": document_sha256,
            "pages": [document.page_range.first, document.page_range.last],
        }
    # The remaining resolved type is local HTML with resolver-computed input hashes.
    return {
        **common,
        "document_sha256": document_sha256,
        "inputs": [
            {"path": input_source.path, "sha256": input_source.sha256}
            for input_source in document.provenance.inputs
        ],
    }


def renderer_identity(documents: Sequence[ResolvedDocument]) -> dict[str, Any]:
    """Describe renderer versions and algorithm revisions used by this build."""
    # Explicit revisions invalidate artifacts when behavior changes without a dependency bump.
    identity: dict[str, Any] = {
        "pymupdf": pymupdf.VersionBind,
        "png_dpi": 144,
        "assembly_revision": "ordered-insert-or-browser-copy-1",
        "extraction_revision": "dpi-144-png-before-text-1",
    }
    # Official-only builds never invoke Playwright, so browser state does not affect their key.
    if any(not isinstance(document, ResolvedOfficialDocument) for document in documents):
        identity["html"] = _browser.browser_renderer_identity()
    return identity


def _insert_official_range(
    manual: pymupdf.Document, official: pymupdf.Document, document: ResolvedOfficialDocument
) -> int:
    """Append one validated one-based official PDF range and return its page count."""
    # Configuration is one-based for users. PyMuPDF's insertion indices are zero-based.
    first_page = document.page_range.first - 1
    last_page = document.page_range.last - 1
    if last_page >= official.page_count:
        raise RuntimeError(
            f"official page range {document.page_range.first}-"
            f"{document.page_range.last} exceeds {official.page_count} pages in "
            f"{document.source_path}"
        )
    manual.insert_pdf(official, from_page=first_page, to_page=last_page, final=0)
    return last_page - first_page + 1


# Mixed HTML and official pages must be inserted in the caller's exact document order.
def _combine_documents(  # noqa: WPS231
    documents: Sequence[ResolvedDocument],
    *,
    html_pdf: Path | None,
    html_page_counts: Sequence[int],
    output_pdf: Path,
) -> None:
    """Assemble browser-rendered and official pages in resolved-document order."""
    # The negative form directly identifies the fast path where no official PDF needs opening.
    if html_pdf is not None and not any(  # noqa: WPS504
        isinstance(document, ResolvedOfficialDocument) for document in documents
    ):
        _ = shutil.copyfile(html_pdf, output_pdf)
        return

    # ExitStack holds every PDF opened at runtime and closes all of them on failure or success.
    with contextlib.ExitStack() as resources:
        manual = resources.enter_context(pymupdf.open())
        html_source = None
        if html_pdf is not None:
            html_source = resources.enter_context(pymupdf.open(html_pdf))
        # Reuse an opened official PDF when the profile selects several ranges from the same file.
        official_sources: dict[Path, pymupdf.Document] = {}

        # HTML documents occupy consecutive ranges in the one browser-rendered source PDF.
        html_page = 0
        html_document = 0
        for document in documents:
            # Official pages can be inserted immediately from their configured physical range.
            if isinstance(document, ResolvedOfficialDocument):
                official = official_sources.get(document.source_path)
                if official is None:
                    official = resources.enter_context(pymupdf.open(document.source_path))
                    official_sources[document.source_path] = official
                _ = _insert_official_range(manual, official, document)
                continue

            # Every non-official input must correspond to the next recorded HTML page range.
            if html_source is None:
                raise RuntimeError("HTML renderer did not produce a source PDF")
            page_count = html_page_counts[html_document]
            manual.insert_pdf(
                html_source, from_page=html_page, to_page=html_page + page_count - 1, final=0
            )
            html_page += page_count
            html_document += 1

        if manual.page_count == 0:
            raise RuntimeError("the selected documents produced an empty manual")

        # Strip volatile source metadata and suppress PyMuPDF's random document identifier.
        manual.set_metadata({})
        manual.save(output_pdf, garbage=4, clean=True, deflate=True, no_new_id=True)


def _write_extracted_page(page: pymupdf.Page, *, page_number: int, pages_dir: Path) -> None:
    """Write one canonical PNG and ordered plain-text representation of a PDF page."""
    # Rasterize first so a text-layer failure cannot leave a text-only page pair.
    pixmap = page.get_pixmap(dpi=144, alpha=False)
    pixmap.save(pages_dir / f"{page_number:04d}.png")
    # Sorted blocks preserve approximate visual reading order without exposing layout metadata.
    blocks = page.get_text("blocks", sort=True)
    text_blocks = (str(block[4]).strip() for block in blocks)
    text = "\n".join(block for block in text_blocks if block)
    if not text:
        raise RuntimeError(f"manual page {page_number} has no usable text layer")
    _ = (pages_dir / f"{page_number:04d}.txt").write_text(f"{text}\n", encoding="utf-8")


def _extract_pages(manual_pdf: Path, *, pages_dir: Path) -> int:
    """Extract canonical PNG/text pairs and return the manual page count."""
    pages_dir.mkdir()
    with pymupdf.open(manual_pdf) as manual:
        if manual.page_count == 0:
            raise RuntimeError("the selected documents produced an empty manual")
        page_count = manual.page_count
        for page_number in range(1, page_count + 1):
            _write_extracted_page(
                manual[page_number - 1], page_number=page_number, pages_dir=pages_dir
            )
        return page_count


def build_artifact(
    documents: Sequence[ResolvedDocument], *, cache_dir: Path, artifact_dir: Path
) -> int:
    """Build one artifact directory and return its page count."""
    # Chromium renders all HTML inputs once. Official PDFs bypass the browser entirely.
    html_documents = [
        document for document in documents if not isinstance(document, ResolvedOfficialDocument)
    ]
    html_pdf = artifact_dir / ".html.pdf" if html_documents else None
    html_page_counts: tuple[int, ...] = ()
    if html_pdf is not None:
        # Translate browser-specific failures into the compiler's public exception boundary.
        try:
            html_page_counts = _browser.render_html(
                html_documents,
                source_root=ktane_content_root(cache_dir),
                keypad_root=keypad_assets_root(),
                output_pdf=html_pdf,
            )
        except _browser.ManualBrowserError as error:
            raise RuntimeError(str(error)) from error

    # Reassemble HTML ranges and official PDF ranges according to the original resolver order.
    manual_pdf = artifact_dir / "handbook.pdf"
    _combine_documents(
        documents, html_pdf=html_pdf, html_page_counts=html_page_counts, output_pdf=manual_pdf
    )
    # Canonical page artifacts always come from the combined final manual.
    page_count = _extract_pages(manual_pdf, pages_dir=artifact_dir / "pages")
    if html_pdf is not None:
        html_pdf.unlink()
    return page_count
