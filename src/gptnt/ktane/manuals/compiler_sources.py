"""Public preparation of pinned source files required by the HTML compiler."""

import hashlib
from importlib.resources import files
from pathlib import Path

import anyio

from gptnt.ktane.manuals import _git, _ktane_content
from gptnt.ktane.manuals._progress import ProgressReporter

KTANE_CONTENT_REPOSITORY = "https://github.com/Timwi/KtaneContent.git"
KTANE_CONTENT_COMMIT = "137cc181b37038ccefeddcb095b402aab8dff5de"

_MERGER_ENTRYPOINT = "More/Manual Merger/index.html"


def ktane_content_root(cache_dir: Path) -> Path:
    """Return the checkout containing the pinned Manual Merger."""
    return cache_dir / "sources" / "ktanecontent" / KTANE_CONTENT_COMMIT


def keypad_assets_root() -> Path:
    """Return the committed 256-pixel Keypad image directory."""
    # Editable checkouts keep assets under storage; built wheels relocate them into the package.
    checkout_root = Path(__file__).resolve().parents[4]
    checkout_assets = checkout_root / "storage" / "manual" / "keypad"
    if checkout_assets.is_dir():
        return checkout_assets
    return Path(str(files("gptnt") / "_manual_keypad"))


def keypad_assets_identity() -> str:
    """Hash the committed Keypad filenames and content for artifact identity."""
    assets = sorted(keypad_assets_root().glob("*.png"))
    if not assets:
        raise ValueError("the committed Keypad asset directory contains no PNG images")
    # Include filenames and separators so renamed or ambiguously concatenated assets invalidate.
    digest = hashlib.sha256()
    for asset in assets:
        digest.update(asset.name.encode())
        digest.update(b"\0")
        digest.update(asset.read_bytes())
    return digest.hexdigest()


async def prepare_compiler_sources(cache_dir: Path) -> None:
    """Materialize the pinned Manual Merger source files."""
    ktane_root = ktane_content_root(cache_dir)
    # The blobless pinned checkout supplies the repository tree without downloading every manual.
    await _git.prepare_repository(
        repository=KTANE_CONTENT_REPOSITORY,
        commit=KTANE_CONTENT_COMMIT,
        destination=anyio.Path(ktane_root),
    )
    # Restore the merger entrypoint and recursively referenced CSS, JavaScript, fonts, and images.
    ktane_paths = await _git.tree_paths(anyio.Path(ktane_root), commit=KTANE_CONTENT_COMMIT)
    _ = await _ktane_content.restore_repository_dependencies(
        ktane_root,
        commit=KTANE_CONTENT_COMMIT,
        paths={_MERGER_ENTRYPOINT},
        repository_paths=ktane_paths,
        reporter=ProgressReporter(),
    )
