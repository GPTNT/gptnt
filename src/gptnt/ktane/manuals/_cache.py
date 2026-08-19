"""Atomic directory publication shared by canonical and variant caches."""

from __future__ import annotations

import shutil
import uuid
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

MANIFEST_NAME = "manifest.json"


def write_manifest(root: Path, manifest: BaseModel) -> None:
    """Write the completion record after every referenced file exists."""
    _ = (root / MANIFEST_NAME).write_text(manifest.model_dump_json(indent=2), encoding="utf-8")


def parse_manifest[ManifestT: BaseModel](
    root: Path, model: type[ManifestT], *, validate: Callable[[Path, ManifestT], None]
) -> ManifestT:
    """Parse a stored manifest and validate each file it references."""
    manifest = model.model_validate_json((root / MANIFEST_NAME).read_bytes())
    validate(root, manifest)
    return manifest


def remove_abandoned_directories(parent: Path, *, digest: str) -> None:
    """Remove unpublished directories for this cache key while holding its lock."""
    for pattern in (f".{digest}.tmp-*", f".{digest}.stale-*"):
        for path in parent.glob(pattern):
            _remove_path(path)


def publish_directory(source: Path, *, destination: Path, digest: str) -> None:
    """Replace a stale directory with one validated unpublished directory."""
    stale_root = destination.parent / f".{digest}.stale-{uuid.uuid4().hex}"
    if destination.exists() or destination.is_symlink():
        _ = destination.replace(stale_root)
    try:
        _ = source.replace(destination)
    except BaseException:
        stale_exists = stale_root.exists() or stale_root.is_symlink()
        destination_absent = not destination.exists() and not destination.is_symlink()
        if stale_exists and destination_absent:
            _ = stale_root.replace(destination)
        raise
    _remove_path(stale_root)


def _remove_path(path: Path) -> None:
    """Remove one exact unpublished cache path, including a partial file or link."""
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)
