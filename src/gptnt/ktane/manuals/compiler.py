"""Compile ordered resolved documents into cached handbook artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pymupdf

from gptnt.ktane.manuals import _browser
from gptnt.ktane.manuals._compiler_sources import (
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
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _input_identity(document: ResolvedDocument) -> dict[str, Any]:
    common: dict[str, Any] = {
        "source": document.source,
        "id": document.document_id,
        "language": document.language,
    }
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
    if isinstance(document, ResolvedOfficialDocument):
        return {
            **common,
            "version": document.provenance.version,
            "url": document.provenance.url,
            "pdf_sha256": _sha256_file(document.source_path),
            "pages": [document.page_range.first, document.page_range.last],
        }
    return {
        **common,
        "document_sha256": _sha256_file(document.source_path),
        "inputs": [
            {"path": source.path, "sha256": source.sha256} for source in document.provenance.inputs
        ],
    }


def _renderer_identity(documents: Sequence[ResolvedDocument]) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "pymupdf": pymupdf.VersionBind,
        "png_dpi": 144,
        "assembly_revision": "ordered-insert-or-browser-copy-1",
        "extraction_revision": "dpi-144-png-before-text-1",
    }
    if any(not isinstance(document, ResolvedOfficialDocument) for document in documents):
        identity["html"] = _browser.browser_renderer_identity()
    return identity


def _artifact_key(inputs: list[dict[str, Any]], renderer: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"inputs": inputs, "renderer": renderer},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _manifest_files(artifact_dir: Path) -> list[dict[str, str]]:
    paths = [artifact_dir / "handbook.pdf"]
    paths.extend(sorted((artifact_dir / "pages").glob("*")))
    return [
        {"path": path.relative_to(artifact_dir).as_posix(), "sha256": _sha256_file(path)}
        for path in paths
    ]


def _validate_artifact(
    artifact_dir: Path,
    *,
    artifact_key: str,
    inputs: list[dict[str, Any]],
    renderer: dict[str, Any],
) -> None:
    manifest_path = artifact_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["artifact"] != artifact_key:
        raise ValueError("artifact key mismatch")
    if manifest["inputs"] != inputs or manifest["renderer"] != renderer:
        raise ValueError("artifact identity mismatch")
    page_count = manifest["page_count"]
    files = manifest["files"]
    if not isinstance(page_count, int) or page_count < 1 or not isinstance(files, list):
        raise ValueError("invalid page or file list")

    expected_paths = {"handbook.pdf"}
    for page_number in range(1, page_count + 1):
        expected_paths.add(f"pages/{page_number:04d}.txt")
        expected_paths.add(f"pages/{page_number:04d}.png")
    listed_paths = {entry["path"] for entry in files}
    if listed_paths != expected_paths:
        raise ValueError("artifact file list mismatch")
    for entry in files:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("artifact file path leaves its directory")
        path = artifact_dir / relative
        if not path.is_file() or _sha256_file(path) != entry["sha256"]:
            raise ValueError("artifact file is missing or has changed")
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
    try:
        _validate_artifact(
            artifact_dir, artifact_key=artifact_key, inputs=inputs, renderer=renderer
        )
    except _INVALID_ARTIFACT_EXCEPTIONS:
        return False
    else:
        return True


def _remove_incomplete(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _insert_official_range(
    handbook: pymupdf.Document, official: pymupdf.Document, document: ResolvedOfficialDocument
) -> int:
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


def _combine_documents(
    documents: Sequence[ResolvedDocument],
    *,
    html_pdf: Path | None,
    html_page_counts: Sequence[int],
    output_pdf: Path,
) -> None:
    if html_pdf is not None and not any(
        isinstance(document, ResolvedOfficialDocument) for document in documents
    ):
        _ = shutil.copyfile(html_pdf, output_pdf)
        return

    handbook = pymupdf.open()
    html_source = pymupdf.open(html_pdf) if html_pdf is not None else None
    official_sources: dict[Path, pymupdf.Document] = {}
    try:
        html_page = 0
        html_document = 0
        for document in documents:
            if isinstance(document, ResolvedOfficialDocument):
                official = official_sources.get(document.source_path)
                if official is None:
                    official = pymupdf.open(document.source_path)
                    official_sources[document.source_path] = official
                _ = _insert_official_range(handbook, official, document)
                continue

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
        handbook.set_metadata({})
        handbook.save(output_pdf, garbage=4, clean=True, deflate=True, no_new_id=True)
    finally:
        if html_source is not None:
            html_source.close()
        for official in official_sources.values():
            official.close()
        handbook.close()


def _write_extracted_page(page: pymupdf.Page, *, page_number: int, pages_dir: Path) -> None:
    pixmap = page.get_pixmap(dpi=144, alpha=False)
    pixmap.save(pages_dir / f"{page_number:04d}.png")
    blocks = page.get_text("blocks", sort=True)
    text = "\n".join(str(block[4]).strip() for block in blocks if str(block[4]).strip())
    if not text:
        raise ManualCompileError(f"handbook page {page_number} has no usable text layer")
    _ = (pages_dir / f"{page_number:04d}.txt").write_text(f"{text}\n", encoding="utf-8")


def _extract_pages(handbook_pdf: Path, *, pages_dir: Path) -> int:
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
    html_documents = [
        document for document in documents if not isinstance(document, ResolvedOfficialDocument)
    ]
    html_pdf = artifact_dir / ".html.pdf" if html_documents else None
    html_page_counts: tuple[int, ...] = ()
    if html_pdf is not None:
        try:
            html_page_counts = _browser.render_html(
                html_documents,
                source_root=ktane_content_root(cache_dir),
                keypad_root=keypad_assets_root(),
                output_pdf=html_pdf,
            )
        except _browser.ManualBrowserError as error:
            raise ManualCompileError(str(error)) from error

    handbook_pdf = artifact_dir / "handbook.pdf"
    _combine_documents(
        documents, html_pdf=html_pdf, html_page_counts=html_page_counts, output_pdf=handbook_pdf
    )
    page_count = _extract_pages(handbook_pdf, pages_dir=artifact_dir / "pages")
    if html_pdf is not None:
        html_pdf.unlink()
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

    inputs = [_input_identity(document) for document in documents]
    renderer = _renderer_identity(documents)
    artifact_key = _artifact_key(inputs, renderer)
    artifacts_dir = cache_dir / _ARTIFACTS_DIRECTORY
    artifact_dir = artifacts_dir / artifact_key
    if _valid_artifact(artifact_dir, artifact_key=artifact_key, inputs=inputs, renderer=renderer):
        return artifact_dir

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
        if not _valid_artifact(
            build_dir, artifact_key=artifact_key, inputs=inputs, renderer=renderer
        ):
            raise ManualCompileError("compiler produced an incomplete artifact")
        _ = build_dir.rename(artifact_dir)
    return artifact_dir
