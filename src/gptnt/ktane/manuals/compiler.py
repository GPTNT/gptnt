"""Compile ordered resolved documents into cached handbook artifacts."""

from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
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

_ARTIFACTS_DIRECTORY = "artifacts"
_INVALID_ARTIFACT_EXCEPTIONS = (
    AttributeError,
    IndexError,
    KeyError,
    OSError,
    TypeError,
    ValueError,
    json.JSONDecodeError,
)


class ManualCompileError(RuntimeError):
    """Selected source documents cannot produce a validated handbook."""


def _sha256_file(path: Path) -> str:
    """Return the hexadecimal SHA-256 digest of one source or artifact file."""
    digest = hashlib.sha256()
    # Stream large PDFs instead of making cache identity proportional to available memory.
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _input_identity(document: ResolvedDocument) -> dict[str, Any]:
    """Describe one resolved input with every value that can affect rendered output."""
    # These fields identify all document variants before source-specific provenance is added.
    common: dict[str, Any] = {
        "source": document.source,
        "id": document.document_id,
        "language": document.language,
    }
    # Modules depend on both their HTML and catalog metadata used by the upstream merger.
    if isinstance(document, ResolvedKtaneContentModule):
        if document.provenance.commit != KTANE_CONTENT_COMMIT:
            raise ManualCompileError(
                "KtaneContent documents must use the compiler's pinned Manual Merger commit "
                f"{KTANE_CONTENT_COMMIT}; found {document.provenance.commit}"
            )
        return {
            **common,
            "commit": document.provenance.commit,
            "document": document.provenance.document,
            "document_sha256": _sha256_file(document.source_path),
            "metadata_document": document.provenance.metadata_document,
            "metadata_sha256": _sha256_file(document.metadata_path),
        }
    # Appendices have HTML provenance but no module metadata document.
    if isinstance(document, ResolvedKtaneContentAppendix):
        if document.provenance.commit != KTANE_CONTENT_COMMIT:
            raise ManualCompileError(
                "KtaneContent documents must use the compiler's pinned Manual Merger commit "
                f"{KTANE_CONTENT_COMMIT}; found {document.provenance.commit}"
            )
        return {
            **common,
            "commit": document.provenance.commit,
            "document": document.provenance.document,
            "document_sha256": _sha256_file(document.source_path),
        }
    # Official inputs are selected PDF page ranges rather than HTML documents.
    if isinstance(document, ResolvedOfficialDocument):
        return {
            **common,
            "version": document.provenance.version,
            "url": document.provenance.url,
            "pdf_sha256": _sha256_file(document.source_path),
            "pages": [document.page_range.first, document.page_range.last],
        }
    # The remaining resolved type is local HTML with resolver-computed input hashes.
    return {
        **common,
        "document_sha256": _sha256_file(document.source_path),
        "inputs": [
            {"path": source.path, "sha256": source.sha256} for source in document.provenance.inputs
        ],
    }


def _renderer_identity(documents: Sequence[ResolvedDocument]) -> dict[str, Any]:
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


def _artifact_key(inputs: list[dict[str, Any]], renderer: dict[str, Any]) -> str:
    """Hash canonical input and renderer identity into the artifact directory key."""
    # Sorted compact JSON makes identity deterministic across runs and machines.
    encoded = json.dumps(
        {"inputs": inputs, "renderer": renderer},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _manifest_files(artifact_dir: Path) -> list[dict[str, str]]:
    """List every published handbook file with its relative path and content hash."""
    # The manifest itself is excluded because it contains this list.
    paths = [artifact_dir / "handbook.pdf"]
    paths.extend(sorted((artifact_dir / "pages").glob("*")))
    return [
        {"path": path.relative_to(artifact_dir).as_posix(), "sha256": _sha256_file(path)}
        for path in paths
    ]


# One validator checks the complete, compact artifact contract and reports its failing invariant.
def _validate_artifact(  # noqa: WPS210,WPS231,WPS238
    artifact_dir: Path,
    *,
    artifact_key: str,
    inputs: list[dict[str, Any]],
    renderer: dict[str, Any],
) -> None:
    """Verify artifact identity, exact file membership, safe paths, and file hashes."""
    manifest_path = artifact_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Identity checks prevent a directory from being reused for different inputs or renderers.
    if manifest["artifact"] != artifact_key:
        raise ValueError("artifact key mismatch")
    if manifest["inputs"] != inputs or manifest["renderer"] != renderer:
        raise ValueError("artifact identity mismatch")
    page_count = manifest["page_count"]
    files = manifest["files"]
    if not isinstance(page_count, int) or page_count < 1 or not isinstance(files, list):
        raise ValueError("invalid page or file list")

    # Each declared page must have exactly one text file and one canonical PNG.
    expected_paths = {"handbook.pdf"}
    for page_number in range(1, page_count + 1):
        expected_paths.add(f"pages/{page_number:04d}.txt")
        expected_paths.add(f"pages/{page_number:04d}.png")
    listed_paths = {entry["path"] for entry in files}
    if listed_paths != expected_paths:
        raise ValueError("artifact file list mismatch")
    # Validate paths before joining them to the artifact directory, then verify their bytes.
    for entry in files:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("artifact file path leaves its directory")
        path = artifact_dir / relative
        if not path.is_file() or _sha256_file(path) != entry["sha256"]:
            raise ValueError("artifact file is missing or has changed")
    # Extra files also make the artifact invalid because the manifest is the complete contract.
    actual_paths = {
        path.relative_to(artifact_dir).as_posix()
        for path in artifact_dir.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if actual_paths != expected_paths:
        raise ValueError("artifact contains unlisted files")


def _valid_artifact(
    artifact_dir: Path,
    *,
    artifact_key: str,
    inputs: list[dict[str, Any]],
    renderer: dict[str, Any],
) -> bool:
    """Return whether an artifact satisfies the complete cache contract."""
    # Missing, malformed, or stale cache state is recoverable and triggers a fresh build.
    try:
        _validate_artifact(
            artifact_dir, artifact_key=artifact_key, inputs=inputs, renderer=renderer
        )
    except _INVALID_ARTIFACT_EXCEPTIONS:
        return False
    else:
        return True


def _remove_incomplete(path: Path) -> None:
    """Remove one invalid artifact path regardless of whether it is a file or directory."""
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _insert_official_range(
    handbook: pymupdf.Document, official: pymupdf.Document, document: ResolvedOfficialDocument
) -> int:
    """Append one validated one-based official PDF range and return its page count."""
    # Configuration is one-based for users; PyMuPDF's insertion indices are zero-based.
    first_page = document.page_range.first - 1
    last_page = document.page_range.last - 1
    if last_page >= official.page_count:
        raise ManualCompileError(
            f"official page range {document.page_range.first}-"
            f"{document.page_range.last} exceeds {official.page_count} pages in "
            f"{document.source_path}"
        )
    handbook.insert_pdf(official, from_page=first_page, to_page=last_page, final=0)
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

    # ExitStack owns every dynamically opened PDF and closes all of them on failure or success.
    with contextlib.ExitStack() as resources:
        handbook = resources.enter_context(pymupdf.open())
        html_source = None
        if html_pdf is not None:
            html_source = resources.enter_context(pymupdf.open(html_pdf))
        # Reuse an opened official PDF when the profile selects several ranges from the same file.
        official_sources: dict[Path, pymupdf.Document] = {}

        # HTML documents occupy consecutive ranges in the single browser-rendered source PDF.
        html_page = 0
        html_document = 0
        for document in documents:
            # Official pages can be inserted immediately from their configured physical range.
            if isinstance(document, ResolvedOfficialDocument):
                official = official_sources.get(document.source_path)
                if official is None:
                    official = resources.enter_context(pymupdf.open(document.source_path))
                    official_sources[document.source_path] = official
                _ = _insert_official_range(handbook, official, document)
                continue

            # Every non-official input must correspond to the next recorded HTML page range.
            if html_source is None:
                raise ManualCompileError("HTML renderer did not produce a source PDF")
            page_count = html_page_counts[html_document]
            handbook.insert_pdf(
                html_source, from_page=html_page, to_page=html_page + page_count - 1, final=0
            )
            html_page += page_count
            html_document += 1

        if handbook.page_count == 0:
            raise ManualCompileError("the selected documents produced an empty handbook")

        # Strip volatile source metadata and suppress PyMuPDF's random document identifier.
        handbook.set_metadata({})
        handbook.save(output_pdf, garbage=4, clean=True, deflate=True, no_new_id=True)


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
        raise ManualCompileError(f"handbook page {page_number} has no usable text layer")
    _ = (pages_dir / f"{page_number:04d}.txt").write_text(f"{text}\n", encoding="utf-8")


def _extract_pages(handbook_pdf: Path, *, pages_dir: Path) -> int:
    """Extract canonical PNG/text pairs and return the handbook page count."""
    pages_dir.mkdir()
    with pymupdf.open(handbook_pdf) as handbook:
        if handbook.page_count == 0:
            raise ManualCompileError("the selected documents produced an empty handbook")
        page_count = handbook.page_count
        for page_number in range(1, page_count + 1):
            _write_extracted_page(
                handbook[page_number - 1], page_number=page_number, pages_dir=pages_dir
            )
        return page_count


def _build_artifact(
    documents: Sequence[ResolvedDocument],
    *,
    cache_dir: Path,
    artifact_dir: Path,
    artifact_key: str,
    inputs: list[dict[str, Any]],
    renderer: dict[str, Any],
) -> None:
    """Build and describe one artifact inside an unpublished temporary directory."""
    # Chromium renders all HTML inputs once; official PDFs bypass the browser entirely.
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
            raise ManualCompileError(str(error)) from error

    # Reassemble HTML ranges and official PDF ranges according to the original resolver order.
    handbook_pdf = artifact_dir / "handbook.pdf"
    _combine_documents(
        documents, html_pdf=html_pdf, html_page_counts=html_page_counts, output_pdf=handbook_pdf
    )
    # Canonical page artifacts always come from the combined final handbook.
    page_count = _extract_pages(handbook_pdf, pages_dir=artifact_dir / "pages")
    if html_pdf is not None:
        html_pdf.unlink()
    # Write the manifest last so a complete manifest always describes existing output files.
    manifest = {
        "artifact": artifact_key,
        "inputs": inputs,
        "renderer": renderer,
        "page_count": page_count,
        "files": _manifest_files(artifact_dir),
    }
    _ = (artifact_dir / "manifest.json").write_text(
        f"{json.dumps(manifest, ensure_ascii=False, separators=(',', ':'))}\n", encoding="utf-8"
    )


def compile_manual(documents: Sequence[ResolvedDocument], *, cache_dir: Path) -> Path:
    """Compile an ordered resolved-document sequence and return its cached artifact path."""
    if not documents:
        raise ValueError("at least one resolved manual document is required")

    # Ordered input identity and renderer identity jointly address the immutable artifact.
    inputs = [_input_identity(document) for document in documents]
    renderer = _renderer_identity(documents)
    artifact_key = _artifact_key(inputs, renderer)
    artifacts_dir = cache_dir / _ARTIFACTS_DIRECTORY
    artifact_dir = artifacts_dir / artifact_key
    # A valid directory is immutable and can be returned without invoking either renderer.
    if _valid_artifact(artifact_dir, artifact_key=artifact_key, inputs=inputs, renderer=renderer):
        return artifact_dir

    # Invalid state at the target key is never reused; replace it through a temporary build.
    _remove_incomplete(artifact_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".manual-build-", dir=artifacts_dir) as temporary:
        build_dir = Path(temporary) / "artifact"
        build_dir.mkdir()
        _build_artifact(
            documents,
            cache_dir=cache_dir,
            artifact_dir=build_dir,
            artifact_key=artifact_key,
            inputs=inputs,
            renderer=renderer,
        )
        # Validate the unpublished output using the same contract applied to cache hits.
        if not _valid_artifact(
            build_dir, artifact_key=artifact_key, inputs=inputs, renderer=renderer
        ):
            raise ManualCompileError("compiler produced an incomplete artifact")
        # Same-filesystem rename publishes the complete validated directory atomically.
        _ = build_dir.rename(artifact_dir)
    return artifact_dir
