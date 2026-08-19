"""Prepared image-dimension variants derived from canonical manual pages."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from filelock import FileLock
from PIL import Image, __version__ as pillow_version

from gptnt.common.hashing import stable_digest
from gptnt.ktane.manuals._artifact import (
    ResizerIdentity,
    VariantManifest,
    VariantPageManifest,
    artifact_path,
    sha256_file,
    validate_variant_files,
)
from gptnt.ktane.manuals._cache import (
    parse_manifest,
    publish_directory,
    remove_abandoned_directories,
    write_manifest,
)
from gptnt.ktane.manuals._compile import load_compiled_artifact
from gptnt.ktane.manuals.artifact import (
    CompiledManualArtifact,
    ManualCompilationError,
    PreparedManualVariant,
)

_VARIANT_CACHE_NAME = "variants"


def prepare_variant(
    artifact: CompiledManualArtifact, *, width: int, height: int
) -> PreparedManualVariant:
    """Prepare or reuse one validated image-dimension variant."""
    if width <= 0 or height <= 0:
        raise ValueError("manual image variant dimensions must be positive")
    canonical = load_compiled_artifact(artifact.path, expected_digest=artifact.digest)
    if canonical is None:
        raise ManualCompilationError("canonical manual artifact is missing or corrupt")
    resizer = _resizer_identity()
    digest = _variant_digest(canonical, width=width, height=height, resizer=resizer)
    variants_root = canonical.path / _VARIANT_CACHE_NAME
    lock_path = variants_root / ".locks" / f"{digest}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(lock_path):
        return _prepare_locked(
            canonical,
            width=width,
            height=height,
            resizer=resizer,
            digest=digest,
            variants_root=variants_root,
        )


def _prepare_locked(
    canonical: CompiledManualArtifact,
    *,
    width: int,
    height: int,
    resizer: ResizerIdentity,
    digest: str,
    variants_root: Path,
) -> PreparedManualVariant:
    remove_abandoned_directories(variants_root, digest=digest)
    variant_root = variants_root / digest
    cached = _load_variant(
        variant_root,
        canonical=canonical,
        expected_digest=digest,
        expected_width=width,
        expected_height=height,
        expected_resizer=resizer,
    )
    if cached is not None:
        return cached
    _rebuild_variant(
        canonical,
        width=width,
        height=height,
        resizer=resizer,
        digest=digest,
        variants_root=variants_root,
    )
    prepared = _load_variant(
        variant_root,
        canonical=canonical,
        expected_digest=digest,
        expected_width=width,
        expected_height=height,
        expected_resizer=resizer,
    )
    if prepared is None:
        raise ManualCompilationError("published manual image variant did not pass validation")
    return prepared


def _rebuild_variant(
    canonical: CompiledManualArtifact,
    *,
    width: int,
    height: int,
    resizer: ResizerIdentity,
    digest: str,
    variants_root: Path,
) -> None:
    temporary_root = Path(tempfile.mkdtemp(prefix=f".{digest}.tmp-", dir=variants_root))
    try:
        _materialize_variant(
            canonical,
            width=width,
            height=height,
            resizer=resizer,
            digest=digest,
            output_dir=temporary_root,
        )
    except BaseException:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise


def _materialize_variant(
    canonical: CompiledManualArtifact,
    *,
    width: int,
    height: int,
    resizer: ResizerIdentity,
    digest: str,
    output_dir: Path,
) -> None:
    manifest = _build_variant(
        canonical,
        width=width,
        height=height,
        resizer=resizer,
        digest=digest,
        output_dir=output_dir,
    )
    write_manifest(output_dir, manifest)
    validate_variant_files(output_dir, manifest)
    publish_directory(
        output_dir, destination=canonical.path / _VARIANT_CACHE_NAME / digest, digest=digest
    )


def _build_variant(
    canonical: CompiledManualArtifact,
    *,
    width: int,
    height: int,
    resizer: ResizerIdentity,
    digest: str,
    output_dir: Path,
) -> VariantManifest:
    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True)
    pages = tuple(
        _resize_page(
            page.image_path,
            page_number=page.page_number,
            width=width,
            height=height,
            output_dir=output_dir,
        )
        for page in canonical.pages
    )
    return VariantManifest(
        canonical_artifact_digest=canonical.digest,
        variant_digest=digest,
        width=width,
        height=height,
        resizer=resizer,
        pages=pages,
    )


def _resize_page(
    source: Path, *, page_number: int, width: int, height: int, output_dir: Path
) -> VariantPageManifest:
    output_path = output_dir / "images" / f"page-{page_number:04d}.png"
    with Image.open(source, formats=("PNG",)) as image:
        resized = image.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
        resized.save(output_path, format="PNG")
    return VariantPageManifest(
        page_number=page_number,
        image_path=output_path.relative_to(output_dir).as_posix(),
        image_sha256=sha256_file(output_path),
    )


def _load_variant(
    root: Path,
    *,
    canonical: CompiledManualArtifact,
    expected_digest: str,
    expected_width: int,
    expected_height: int,
    expected_resizer: ResizerIdentity,
) -> PreparedManualVariant | None:
    manifest = _read_variant_manifest(root)
    if manifest is None or not _variant_matches(
        manifest,
        canonical=canonical,
        expected_digest=expected_digest,
        expected_width=expected_width,
        expected_height=expected_height,
        expected_resizer=expected_resizer,
    ):
        return None
    image_paths = tuple(artifact_path(root, page.image_path) for page in manifest.pages)
    return PreparedManualVariant(
        digest=manifest.variant_digest, path=root, canonical=canonical, image_paths=image_paths
    )


def _read_variant_manifest(root: Path) -> VariantManifest | None:
    try:
        manifest = parse_manifest(root, VariantManifest, validate=validate_variant_files)
    except (OSError, ValueError):
        return None
    return manifest


def _variant_matches(
    manifest: VariantManifest,
    *,
    canonical: CompiledManualArtifact,
    expected_digest: str,
    expected_width: int,
    expected_height: int,
    expected_resizer: ResizerIdentity,
) -> bool:
    identity_matches = _variant_metadata_matches(
        manifest,
        canonical=canonical,
        expected_digest=expected_digest,
        expected_width=expected_width,
        expected_height=expected_height,
        expected_resizer=expected_resizer,
    )
    return (
        identity_matches
        and _variant_digest(
            canonical, width=manifest.width, height=manifest.height, resizer=manifest.resizer
        )
        == expected_digest
    )


def _variant_metadata_matches(
    manifest: VariantManifest,
    *,
    canonical: CompiledManualArtifact,
    expected_digest: str,
    expected_width: int,
    expected_height: int,
    expected_resizer: ResizerIdentity,
) -> bool:
    artifact_matches = manifest.canonical_artifact_digest == canonical.digest
    dimensions_match = manifest.width == expected_width and manifest.height == expected_height
    return (
        artifact_matches
        and manifest.variant_digest == expected_digest
        and dimensions_match
        and manifest.resizer == expected_resizer
    )


def _variant_digest(
    canonical: CompiledManualArtifact, *, width: int, height: int, resizer: ResizerIdentity
) -> str:
    return stable_digest(
        {
            "canonical_artifact_digest": canonical.digest,
            "width": width,
            "height": height,
            "resizer": resizer.model_dump(mode="json"),
        }
    )


def _resizer_identity() -> ResizerIdentity:
    return ResizerIdentity(implementation=f"pillow:{pillow_version}", algorithm="lanczos-exact")
