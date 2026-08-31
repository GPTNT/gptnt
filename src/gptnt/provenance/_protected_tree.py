from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal

import pygit2

if TYPE_CHECKING:
    from collections.abc import Iterable

_DIGEST_DOMAIN = b"gptnt-protected-tree-v1\0"
_EXCLUDED_NAMES = frozenset(("__pycache__", ".DS_Store"))

type ProtectedObjectKind = Literal["directory", "file", "symlink"]


class BenchmarkIntegrityError(RuntimeError):
    """The repository cannot produce a benchmark integrity result."""


@dataclass(frozen=True, kw_only=True)
class _ProtectedEntry:
    """One canonical directory, regular file, or symbolic-link record."""

    path: str
    """Repository-relative UTF-8 path."""

    kind: ProtectedObjectKind
    """Filesystem object kind included in the digest."""

    content: bytes
    """Canonical file content, symlink target bytes, or empty bytes for a directory."""


@dataclass(frozen=True, kw_only=True)
class _ProtectedTree:
    """Canonical protected roots and the filesystem objects found below them."""

    roots: tuple[str, ...]
    entries: tuple[_ProtectedEntry, ...]

    @property
    def digest(self) -> str:
        """SHA-256 identity of the v1 length-prefixed tree serialization."""
        stream = hashlib.sha256()
        stream.update(_DIGEST_DOMAIN)
        for root in sorted(self.roots, key=str.encode):
            _update_field(stream, b"root")
            _update_field(stream, root.encode("utf-8"))
        for entry in sorted(self.entries, key=lambda protected: protected.path.encode("utf-8")):
            _update_field(stream, b"entry")
            _update_field(stream, entry.path.encode("utf-8"))
            _update_field(stream, entry.kind.encode("ascii"))
            _update_field(stream, entry.content)
        return f"sha256:{stream.hexdigest()}"


def _update_field(stream: hashlib._Hash, payload: bytes) -> None:
    """Write one unambiguous length-prefixed field to the digest stream."""
    stream.update(len(payload).to_bytes(8, "big"))
    stream.update(payload)


def _canonical_file_content(content: bytes) -> bytes:
    """Normalize CRLF in UTF-8 text and preserve non-UTF-8 file bytes."""
    try:
        _ = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return content
    return content.replace(b"\r\n", b"\n")


def _normalize_roots(roots: Iterable[str]) -> tuple[str, ...]:
    """Return unique repository-relative roots in UTF-8 byte order."""
    normalized: set[str] = set()
    for root in roots:
        path = PurePosixPath(root)
        normalized_root = str(path)
        components = root.split("/")
        if (
            path.is_absolute()
            or normalized_root == "."
            or any(component in {".", ".."} for component in components)
            or "\0" in root
        ):
            raise BenchmarkIntegrityError(
                f"Protected root {root!r} must be a normalized repository-relative path"
            )
        try:
            encoded = normalized_root.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise BenchmarkIntegrityError(f"Protected root {root!r} is not valid UTF-8") from error
        normalized.add(encoded.decode("utf-8"))
    return tuple(sorted(normalized, key=str.encode))


def _decode_git_name(raw_name: bytes, *, parent: str) -> str:
    """Decode a Git tree entry name under the v1 UTF-8 path policy."""
    try:
        return raw_name.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        location = f" under {parent!r}" if parent else ""
        raise BenchmarkIntegrityError(
            f"Protected Git path{location} is not valid UTF-8"
        ) from error


def _decode_checkout_name(name: str, *, parent: str) -> str:
    """Convert a checkout entry name to the v1 UTF-8 path representation."""
    try:
        return os.fsencode(name).decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        location = f" under {parent!r}" if parent else ""
        raise BenchmarkIntegrityError(
            f"Protected checkout path{location} is not valid UTF-8"
        ) from error


def _git_entry_at(tree: pygit2.Tree, root: str) -> pygit2.Object | None:
    """Return the Git object at a protected root, or `None` when it is absent."""
    current = tree
    entry: pygit2.Object | None = None
    components = root.split("/")
    for index, component in enumerate(components):
        component_bytes = component.encode("utf-8")
        entry = next(
            (candidate for candidate in current if candidate.raw_name == component_bytes), None
        )
        if entry is None:
            return None
        if index < len(components) - 1:
            if not isinstance(entry, pygit2.Tree):
                return None
            current = entry
    return entry


def _collect_git_entry(  # noqa: WPS231 - Git object-kind validation is one recursive traversal.
    entry: pygit2.Object, *, path: str, entries: dict[str, _ProtectedEntry]
) -> bool:
    """Add one Git object and its included descendants to `entries`.

    Return whether the object contributes an entry. Excluded names and directories containing no
    included descendants return `False`.
    """
    mode = int(entry.filemode)
    name = path.rsplit("/", maxsplit=1)[-1]
    # Exclusions are path-component rules and therefore apply before inspecting the object kind.
    if name in _EXCLUDED_NAMES:
        return False
    if isinstance(entry, pygit2.Tree):
        # Git does not store empty directories. Retain a directory only when a child is retained.
        included = False
        for child in entry:
            if child.raw_name is None:
                raise BenchmarkIntegrityError(f"Protected Git path under {path!r} has no name")
            child_name = _decode_git_name(child.raw_name, parent=path)
            child_path = f"{path}/{child_name}"
            included = _collect_git_entry(child, path=child_path, entries=entries) or included
        if included:
            entries[path] = _ProtectedEntry(path=path, kind="directory", content=b"")
        return included
    if not isinstance(entry, pygit2.Blob):
        raise BenchmarkIntegrityError(f"Unsupported protected Git object at {path!r}")
    # File modes are excluded because checkout executable bits are not portable across platforms.
    if mode == int(pygit2.enums.FileMode.LINK):
        kind: ProtectedObjectKind = "symlink"
    elif mode in {int(pygit2.enums.FileMode.BLOB), int(pygit2.enums.FileMode.BLOB_EXECUTABLE)}:
        kind = "file"
    else:
        raise BenchmarkIntegrityError(f"Unsupported protected Git mode {mode:o} at {path!r}")
    content = bytes(entry.data)
    entries[path] = _ProtectedEntry(
        path=path,
        kind=kind,
        content=_canonical_file_content(content) if kind == "file" else content,
    )
    return True


def build_git_protected_tree(tree: pygit2.Tree, *, roots: tuple[str, ...]) -> _ProtectedTree:
    """Build a canonical protected tree from a Git commit tree."""
    normalized_roots = _normalize_roots(roots)
    entries: dict[str, _ProtectedEntry] = {}
    for root in normalized_roots:
        entry = _git_entry_at(tree, root)
        if entry is not None:
            _ = _collect_git_entry(entry, path=root, entries=entries)
    return _ProtectedTree(
        roots=normalized_roots,
        entries=tuple(entries[path] for path in sorted(entries, key=str.encode)),
    )


def _collect_checkout_path(  # noqa: WPS231 - Filesystem validation is one recursive traversal.
    path: Path, *, relative_path: str, entries: dict[str, _ProtectedEntry]
) -> bool:
    """Add one checkout object and its included descendants to `entries`.

    Return whether the object contributes an entry. Symbolic links are recorded by target and are
    never followed. UTF-8 regular files use the v1 line-ending normalization.
    """
    path_stat = path.lstat()
    name = relative_path.rsplit("/", maxsplit=1)[-1]
    # Apply the same path-component exclusions used while walking the release tree.
    if name in _EXCLUDED_NAMES:
        return False
    # Test for a link before directories and files so a link cannot escape the protected roots.
    if stat.S_ISLNK(path_stat.st_mode):
        entries[relative_path] = _ProtectedEntry(
            path=relative_path, kind="symlink", content=os.fsencode(path.readlink())
        )
        return True
    if stat.S_ISREG(path_stat.st_mode):
        entries[relative_path] = _ProtectedEntry(
            path=relative_path, kind="file", content=_canonical_file_content(path.read_bytes())
        )
        return True
    if stat.S_ISDIR(path_stat.st_mode):
        # Match Git's tree model by omitting directories with no included descendants.
        included = False
        with os.scandir(path) as children:
            for child in children:
                child_name = _decode_checkout_name(child.name, parent=relative_path)
                child_relative_path = f"{relative_path}/{child_name}"
                included = (
                    _collect_checkout_path(
                        Path(child.path), relative_path=child_relative_path, entries=entries
                    )
                    or included
                )
        if included:
            entries[relative_path] = _ProtectedEntry(
                path=relative_path, kind="directory", content=b""
            )
        return included
    raise BenchmarkIntegrityError(f"Unsupported protected checkout object at {relative_path!r}")


def _resolve_checkout_root_path(repository_root: Path, root: str) -> Path | None:
    """Resolve a protected root without traversing a non-directory parent component."""
    current = repository_root
    components = root.split("/")
    for index, component in enumerate(components):
        current /= component
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            return None
        if index < len(components) - 1 and not stat.S_ISDIR(mode):
            raise BenchmarkIntegrityError(
                f"Protected root {root!r} crosses non-directory path {str(current)!r}"
            )
    return current


def build_checkout_protected_tree(
    repository_root: Path, *, roots: tuple[str, ...]
) -> _ProtectedTree:
    """Build a canonical protected tree from the current checkout."""
    normalized_roots = _normalize_roots(roots)
    entries: dict[str, _ProtectedEntry] = {}
    for root in normalized_roots:
        root_path = _resolve_checkout_root_path(repository_root, root)
        if root_path is not None:
            _ = _collect_checkout_path(root_path, relative_path=root, entries=entries)
    return _ProtectedTree(
        roots=normalized_roots,
        entries=tuple(entries[path] for path in sorted(entries, key=str.encode)),
    )


def find_changed_protected_paths(
    release: _ProtectedTree, checkout: _ProtectedTree
) -> tuple[str, ...]:
    """Return paths whose canonical entries differ between two protected trees."""
    release_by_path = {entry.path: entry for entry in release.entries}
    checkout_by_path = {entry.path: entry for entry in checkout.entries}
    return tuple(
        sorted(
            (
                path
                for path in release_by_path.keys() | checkout_by_path.keys()
                if release_by_path.get(path) != checkout_by_path.get(path)
            ),
            key=str.encode,
        )
    )
