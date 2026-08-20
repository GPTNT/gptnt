"""Build the fixed-name GPTNT release assets."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import ZIP_DEFLATED

import pygit2
import repro_tarfile
from repro_zipfile import ReproducibleZipFile

from gptnt.provenance import BenchmarkIntegrityError, check_benchmark_integrity
from gptnt.provenance.integrity import RELEASE_TAG_PATTERN

if TYPE_CHECKING:
    from collections.abc import Sequence

_ARCHIVES = ("gptnt.tar.gz", "gptnt.zip")
_ASSETS = ("gptnt.tar.gz", "gptnt.tar.gz.sha256", "gptnt.zip", "gptnt.zip.sha256")
_DIRECTORIES = ("src", "configs", "runs", "scripts", "storage", "docs")
_ROOT_FILES = (
    ".gitattributes",
    ".gitignore",
    "CHANGELOG.md",
    "LICENSE",
    "README.md",
    "docker-compose.yml",
    "mise.toml",
    "pyproject.toml",
    "uv.lock",
)
_SPARSE_PATTERNS = (
    *(f"/{path}/" for path in _DIRECTORIES),
    "!/storage/keys/",
    *(f"/{path}" for path in _ROOT_FILES),
)
_ARCHIVE_ENVIRONMENT = {
    "REPRO_TARFILE_DIR_MODE": "755",
    "REPRO_TARFILE_GID": "0",
    "REPRO_TARFILE_GNAME": "",
    "REPRO_TARFILE_UID": "0",
    "REPRO_TARFILE_UNAME": "",
    "REPRO_ZIPFILE_DIR_MODE": "755",
}


class BundleError(RuntimeError):
    """The requested release bundle cannot be built."""


def _git(repository: Path, *arguments: str, input_bytes: bytes | None = None) -> bytes:
    """Run a release-tooling Git operation and translate command failures."""
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(repository), *arguments],
            check=True,
            input=input_bytes,
            capture_output=True,
            env=os.environ | {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"},
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", b"").decode(errors="replace").strip()
        raise BundleError(f"git {' '.join(arguments)} failed: {detail}") from error
    return result.stdout


def _open_repository(path: Path) -> pygit2.Repository:
    """Open the repository containing `path` and report a bundle-specific error."""
    discovered = pygit2.discover_repository(os.fspath(path))
    if discovered is None:
        raise BundleError(f"Repository {path} is not a Git repository")
    return pygit2.Repository(discovered)


def _tag_commit(repository: pygit2.Repository, tag: str) -> pygit2.Commit:
    """Return the commit directly targeted by an annotated release tag."""
    if re.fullmatch(RELEASE_TAG_PATTERN, tag, re.ASCII) is None:
        raise BundleError(f"Tag {tag!r} must match vMAJOR.MINOR.PATCH without leading zeroes")

    try:
        reference = repository.references[f"refs/tags/{tag}"]
        tag_object = repository[reference.target]
    except KeyError as error:
        raise BundleError(f"Repository has no tag {tag!r}") from error
    if not isinstance(tag_object, pygit2.Tag):
        raise BundleError(f"Tag {tag!r} is not annotated")

    commit = repository[tag_object.target]
    if not isinstance(commit, pygit2.Commit):
        raise BundleError(f"Annotated tag {tag!r} must point directly to a commit")
    return commit


def _checkout(source: Path, destination: Path, tag: str, expected_commit: pygit2.Oid) -> None:
    """Stage the requested tag as a detached, depth-one sparse checkout."""
    repository = pygit2.init_repository(destination)
    _ = repository.remotes.create("origin", os.fspath(source))
    tag_ref = f"refs/tags/{tag}"
    # libgit2 cannot create a depth-one checkout from a local repository.
    _git(destination, "fetch", "--depth=1", "--no-tags", "origin", f"{tag_ref}:{tag_ref}")

    commit = _tag_commit(repository, tag)
    if commit.id != expected_commit:
        raise BundleError(f"Fetched tag {tag!r} changed while the bundle was being built")
    repository.set_head(commit.id)
    repository.checkout_tree(commit, strategy=pygit2.GIT_CHECKOUT_FORCE)

    # pygit2 does not expose sparse checkout or its skip-worktree index flags.
    _git(
        destination,
        "sparse-checkout",
        "set",
        "--no-cone",
        "--stdin",
        input_bytes=("\n".join(_SPARSE_PATTERNS) + "\n").encode(),
    )
    _git(destination, "diff", "--quiet", "HEAD", "--")
    _sanitize_repository(repository, destination)

    integrity = check_benchmark_integrity(destination)
    if (
        integrity.release_tag != tag
        or integrity.release_commit != str(expected_commit)
        or integrity.protected_content_modified
    ):
        raise BundleError("Staged checkout does not match the requested release")


def _sanitize_repository(repository: pygit2.Repository, destination: Path) -> None:
    """Remove checkout-specific Git metadata while retaining provenance state."""
    # Rebuild the index so optional cache extensions cannot record the temporary checkout path.
    skipped = [
        record[2:]
        for record in _git(destination, "ls-files", "-t", "-z").rstrip(b"\0").split(b"\0")
        if record.startswith(b"S ")
    ]
    (destination / ".git/index").unlink()
    _git(destination, "read-tree", "HEAD")
    if skipped:
        _git(
            destination,
            "update-index",
            "-z",
            "--skip-worktree",
            "--stdin",
            input_bytes=b"\0".join(skipped) + b"\0",
        )
    repository.remotes.delete("origin")

    # The tag, detached HEAD, index, shallow boundary, and objects remain in .git.
    git_directory = destination / ".git"
    for name in ("FETCH_HEAD", "description", "logs", "hooks"):
        path = git_directory / name
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


def _write_archives(checkout: Path, output_dir: Path, *, timestamp: int) -> None:
    """Write both archive formats and their checksums from one ordered path list."""
    paths = [checkout, *sorted(checkout.rglob("*"), key=lambda path: path.as_posix())]
    environment = _ARCHIVE_ENVIRONMENT | {"SOURCE_DATE_EPOCH": str(timestamp)}

    # Pin the libraries' supported metadata controls so caller environment cannot change output.
    os.environ.update(environment)
    with repro_tarfile.open(output_dir / _ARCHIVES[0], "w:gz") as archive:
        for path in paths:
            os.environ["REPRO_TARFILE_FILE_MODE"] = "755" if path.stat().st_mode & 0o111 else "644"
            archive.add(path, arcname=path.relative_to(checkout.parent), recursive=False)
    with ReproducibleZipFile(output_dir / _ARCHIVES[1], "w", ZIP_DEFLATED) as archive:
        for path in paths:
            os.environ["REPRO_ZIPFILE_FILE_MODE"] = "755" if path.stat().st_mode & 0o111 else "644"
            archive.write(path, arcname=path.relative_to(checkout.parent))

    for archive_name in _ARCHIVES:
        archive = output_dir / archive_name
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        (output_dir / f"{archive_name}.sha256").write_text(
            f"{digest}  {archive_name}\n", encoding="utf-8", newline="\n"
        )


def build_bundle(*, tag: str, repository: Path, output_dir: Path) -> None:
    """Build the four release assets for `tag` without reading the source worktree."""
    source = _open_repository(repository.resolve())
    commit = _tag_commit(source, tag)
    source_path = Path(source.workdir or source.path)

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".gptnt-release-", dir=output_dir) as temporary:
        temporary_directory = Path(temporary)
        checkout = temporary_directory / "gptnt"
        _checkout(source_path, checkout, tag, commit.id)
        _write_archives(checkout, temporary_directory, timestamp=commit.commit_time)
        for asset in _ASSETS:
            (temporary_directory / asset).replace(output_dir / asset)


def _parser() -> argparse.ArgumentParser:
    """Define the standalone builder interface and its output contract."""
    parser = argparse.ArgumentParser(
        description="Build fixed-name tar and ZIP assets from an annotated release tag.",
        epilog="Outputs: " + ", ".join(_ASSETS),
    )
    parser.add_argument("--tag", required=True, help="annotated vMAJOR.MINOR.PATCH release tag")
    parser.add_argument("--repository", required=True, type=Path, help="source Git repository")
    parser.add_argument("--output-dir", required=True, type=Path, help="release asset directory")
    return parser


def main(arguments: Sequence[str] | None = None) -> None:
    """Build release assets from parsed command-line arguments."""
    parser = _parser()
    options = parser.parse_args(arguments)
    try:
        build_bundle(tag=options.tag, repository=options.repository, output_dir=options.output_dir)
    except (BenchmarkIntegrityError, BundleError, pygit2.GitError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
