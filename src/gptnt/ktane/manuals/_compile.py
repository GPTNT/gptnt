"""Canonical manual compilation and cache policy."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pymupdf
from bs4 import __version__ as beautifulsoup_version
from filelock import FileLock
from pydantic_core import to_jsonable_python

from gptnt.common.hashing import stable_digest
from gptnt.ktane.manuals._artifact import (
    ArtifactManifest,
    PageManifest,
    RendererIdentity,
    ResolvedInputManifest,
    artifact_path,
    sha256_file,
    validate_artifact_files,
)
from gptnt.ktane.manuals._cache import (
    parse_manifest,
    publish_directory,
    remove_abandoned_directories,
    write_manifest,
)
from gptnt.ktane.manuals._render import RenderedPage, render_document
from gptnt.ktane.manuals.artifact import (
    CompiledManualArtifact,
    CompiledManualPage,
    ManualCompilationError,
)
from gptnt.ktane.manuals.resolution import (
    ResolvedDocument,
    ResolvedKtaneContentModule,
    ResolvedOfficialDocument,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pydantic import JsonValue

    from gptnt.ktane.manuals.profile import ManualProfile

_CANONICAL_CACHE_NAME = "compiled"
_COMPILER_SCHEMA = "gptnt.manual.v1"
_RULE_SEED = 1


@dataclass(frozen=True, kw_only=True)
class _CanonicalBuild:
    profile: ManualProfile
    documents: tuple[ResolvedDocument, ...]
    renderer: RendererIdentity
    resolved_inputs: tuple[ResolvedInputManifest, ...]
    digest: str
    compiled_root: Path
    artifact_root: Path


def compile_canonical(
    profile: ManualProfile, resolved_documents: Sequence[ResolvedDocument], *, cache_dir: Path
) -> CompiledManualArtifact:
    """Compile or reuse one validated canonical manual."""
    documents = tuple(resolved_documents)
    if not documents:
        raise ManualCompilationError("a compiled manual requires at least one resolved document")
    renderer = renderer_identity()
    resolved_inputs = resolved_input_manifests(documents)
    digest = canonical_digest(
        profile=profile.model_dump(mode="json"),
        compiler_schema=_COMPILER_SCHEMA,
        rule_seed=_RULE_SEED,
        renderer=renderer,
        resolved_inputs=resolved_inputs,
    )
    compiled_root = cache_dir / _CANONICAL_CACHE_NAME
    build = _CanonicalBuild(
        profile=profile,
        documents=documents,
        renderer=renderer,
        resolved_inputs=resolved_inputs,
        digest=digest,
        compiled_root=compiled_root,
        artifact_root=compiled_root / digest,
    )
    return _prepare_canonical(build)


def load_compiled_artifact(root: Path, *, expected_digest: str) -> CompiledManualArtifact | None:
    """Return a cache hit only when the manifest identity and all files validate."""
    manifest = _read_valid_manifest(root)
    if manifest is None or not _manifest_matches(manifest, expected_digest=expected_digest):
        return None
    pages = tuple(
        CompiledManualPage(
            page_number=page.page_number,
            document_id=page.document_id,
            document_page_number=page.document_page_number,
            text_path=artifact_path(root, page.text_path),
            image_path=artifact_path(root, page.image_path),
        )
        for page in manifest.pages
    )
    return CompiledManualArtifact(digest=manifest.artifact_digest, path=root, pages=pages)


def renderer_identity() -> RendererIdentity:
    """Describe every controlled runtime that changes canonical page bytes."""
    return RendererIdentity(
        html=f"beautifulsoup:{beautifulsoup_version}+pymupdf-story:{pymupdf.__version__}:a4",
        pages=f"pymupdf:{pymupdf.__version__}:144dpi",
    )


def resolved_input_manifests(
    documents: tuple[ResolvedDocument, ...],
) -> tuple[ResolvedInputManifest, ...]:
    """Capture source content and provenance before rendering begins."""
    return tuple(
        _resolved_input(document, index=index) for index, document in enumerate(documents)
    )


def canonical_digest(
    *,
    profile: JsonValue,
    compiler_schema: str,
    rule_seed: int,
    renderer: RendererIdentity,
    resolved_inputs: tuple[ResolvedInputManifest, ...],
) -> str:
    """Identify canonical output from all content-affecting compiler inputs."""
    return stable_digest(
        {
            "profile": profile,
            "compiler_schema": compiler_schema,
            "rule_seed": rule_seed,
            "renderer": renderer.model_dump(mode="json"),
            "resolved_inputs": [source.model_dump(mode="json") for source in resolved_inputs],
        }
    )


def _prepare_canonical(build: _CanonicalBuild) -> CompiledManualArtifact:
    lock_path = build.compiled_root / ".locks" / f"{build.digest}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(lock_path):
        remove_abandoned_directories(build.compiled_root, digest=build.digest)
        cached = load_compiled_artifact(build.artifact_root, expected_digest=build.digest)
        if cached is not None:
            return cached
        _rebuild_canonical(build)
        compiled = load_compiled_artifact(build.artifact_root, expected_digest=build.digest)
        if compiled is None:
            raise ManualCompilationError("published manual artifact did not pass validation")
        return compiled


def _rebuild_canonical(build: _CanonicalBuild) -> None:
    temporary_root = Path(
        tempfile.mkdtemp(prefix=f".{build.digest}.tmp-", dir=build.compiled_root)
    )
    try:
        _materialize_canonical(build, output_dir=temporary_root)
    except BaseException:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise


def _materialize_canonical(build: _CanonicalBuild, *, output_dir: Path) -> None:
    manifest = _build_manifest(build, output_dir=output_dir)
    current_inputs = resolved_input_manifests(build.documents)
    if current_inputs != build.resolved_inputs:
        raise ManualCompilationError("a resolved manual input changed during compilation")
    write_manifest(output_dir, manifest)
    validate_artifact_files(output_dir, manifest)
    publish_directory(output_dir, destination=build.artifact_root, digest=build.digest)


def _resolved_input(document: ResolvedDocument, *, index: int) -> ResolvedInputManifest:
    provenance = to_jsonable_python(asdict(document.provenance))
    metadata_sha256 = None
    first_page = None
    last_page = None
    if isinstance(document, ResolvedKtaneContentModule):
        metadata_sha256 = sha256_file(document.metadata_path)
    elif isinstance(document, ResolvedOfficialDocument):
        first_page = document.page_range.first
        last_page = document.page_range.last
    return ResolvedInputManifest(
        document_index=index,
        document_id=document.document_id,
        source=document.source,
        language=document.language,
        supports_requested_rule_seed=document.supports_requested_rule_seed,
        provenance=provenance,
        source_sha256=sha256_file(document.source_path),
        metadata_sha256=metadata_sha256,
        first_page=first_page,
        last_page=last_page,
    )


def _build_manifest(build: _CanonicalBuild, *, output_dir: Path) -> ArtifactManifest:
    pages: list[PageManifest] = []
    for document, resolved_input in zip(build.documents, build.resolved_inputs, strict=True):
        for rendered in render_document(
            document, output_dir=output_dir, first_page_number=len(pages) + 1
        ):
            pages.append(
                _page_manifest(rendered, resolved_input, output_dir=output_dir, pages=pages)
            )
    return ArtifactManifest(
        compiler_schema=_COMPILER_SCHEMA,
        rule_seed=_RULE_SEED,
        renderer=build.renderer,
        artifact_digest=build.digest,
        profile=build.profile.model_dump(mode="json"),
        resolved_inputs=build.resolved_inputs,
        pages=tuple(pages),
    )


def _page_manifest(
    rendered: RenderedPage,
    resolved_input: ResolvedInputManifest,
    *,
    output_dir: Path,
    pages: list[PageManifest],
) -> PageManifest:
    return PageManifest(
        page_number=len(pages) + 1,
        document_index=resolved_input.document_index,
        document_page_number=rendered.document_page_number,
        document_id=resolved_input.document_id,
        source=resolved_input.source,
        provenance=resolved_input.provenance,
        text_path=rendered.text_path.relative_to(output_dir).as_posix(),
        text_sha256=sha256_file(rendered.text_path),
        image_path=rendered.image_path.relative_to(output_dir).as_posix(),
        image_sha256=sha256_file(rendered.image_path),
    )


def _read_valid_manifest(root: Path) -> ArtifactManifest | None:
    try:
        manifest = parse_manifest(root, ArtifactManifest, validate=validate_artifact_files)
    except (OSError, ValueError):
        return None
    return manifest


def _manifest_matches(manifest: ArtifactManifest, *, expected_digest: str) -> bool:
    if manifest.compiler_schema != _COMPILER_SCHEMA or manifest.rule_seed != _RULE_SEED:
        return False
    calculated_digest = canonical_digest(
        profile=manifest.profile,
        compiler_schema=manifest.compiler_schema,
        rule_seed=manifest.rule_seed,
        renderer=manifest.renderer,
        resolved_inputs=manifest.resolved_inputs,
    )
    return manifest.artifact_digest == expected_digest == calculated_digest
