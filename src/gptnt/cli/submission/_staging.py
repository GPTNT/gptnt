"""Local, no-network parts of a submit: find the bundle dirs, copy one, and preview a dry run.

None of this touches GitHub, so it stays out of the git/GitHub plumbing in `_remote`.
"""

import shutil
from pathlib import Path

from rich.console import Console

console = Console()


def all_bundle_dirs(submission_dir: Path) -> list[Path]:
    """Every top-level bundle directory under submission_dir, name-sorted.

    Each is one bundle (`YYYYMMDD_<display-slug>_<capfp8>_<suite>_<ver>`), the boundary for one
    pull request.
    """
    if not submission_dir.exists():
        raise FileNotFoundError(f"Expected a submissions directory at {submission_dir}")
    bundle_dirs = sorted(path for path in submission_dir.iterdir() if path.is_dir())
    if not bundle_dirs:
        raise FileNotFoundError(f"No bundle submission directories found under {submission_dir}")
    return bundle_dirs


def copy_bundle(bundle_dir: Path, submission_dir: Path, clone_dir: Path) -> list[str]:
    """Copy one bundle's subtree into clone_dir under the repo's `submissions/` tree.

    Returns repo-relative paths of the written files (for staging), each starting
    `submissions/<bundle>/...`.
    """
    rel_paths: list[str] = []
    for src_file in bundle_dir.rglob("*"):
        if not src_file.is_file():
            continue
        rel = Path("submissions") / src_file.relative_to(submission_dir)
        destination = clone_dir / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        _ = shutil.copy2(src_file, destination)
        rel_paths.append(str(rel))
    return rel_paths


def report_dry_run(
    *,
    bundle: str,
    branch: str,
    head: str,
    rel_paths: list[str],
    slug: str,
    base: str,
    title: str,
    body: str,
) -> None:
    """Print what a real run would push and open for one bundle, without touching GitHub."""
    tag = f"[yellow]DRY RUN [{bundle}][/yellow]"
    push_target = "your fork" if ":" in head else "the upstream repo (you have push access)"
    console.print(f"{tag}: would force-push branch {branch!r} to {push_target}")
    console.print(f"{tag}: would stage {len(rel_paths)} file(s):")
    for path in rel_paths:
        console.print(f"  - {path}")
    console.print(f"{tag}: would open PR {title!r} against {slug}@{base} (head {head})")
    if body:
        console.print(f"{tag}: PR body:\n{body}")
