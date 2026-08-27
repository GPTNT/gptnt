from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal, Protocol

import pygit2

if TYPE_CHECKING:
    from collections.abc import Iterable

_DIGEST_DOMAIN = b"gptnt-protected-tree-v1\0"
_EXCLUDED_DIRECTORY_NAMES = frozenset({"__pycache__"})
_EXCLUDED_FILE_NAMES = frozenset({".DS_Store"})

type ProtectedObjectKind = Literal["directory", "file", "symlink"]


class BenchmarkIntegrityError(RuntimeError):
    """The repository cannot supply a benchmark integrity result."""


class _DigestStream(Protocol):
    def update(self, data: bytes) -> None: ...


@dataclass(frozen=True, kw_only=True)
class _ProtectedEntry:
    path: str
    kind: ProtectedObjectKind
    mode: int
    content: bytes


@dataclass(frozen=True, kw_only=True)
class _ProtectedTree:
    roots: tuple[str, ...]
    entries: tuple[_ProtectedEntry, ...]

    @property
    def digest(self) -> str:
        stream = hashlib.sha256()
        stream.update(_DIGEST_DOMAIN)
        for root in sorted(self.roots, key=str.encode):
            _update_field(stream, b"root")
            _update_field(stream, root.encode("utf-8"))
        for entry in sorted(self.entries, key=lambda item: item.path.encode("utf-8")):
            _update_field(stream, b"entry")
            _update_field(stream, entry.path.encode("utf-8"))
            _update_field(stream, entry.kind.encode("ascii"))
            _update_field(stream, f"{entry.mode:o}".encode("ascii"))
            _update_field(stream, entry.content)
        return f"sha256:{stream.hexdigest()}"


def _update_field(stream: _DigestStream, value: bytes) -> None:
    stream.update(len(value).to_bytes(8, "big"))
    stream.update(value)


def _normalize_roots(roots: Iterable[str]) -> tuple[str, ...]:
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
            raise BenchmarkIntegrityError(
                f"Protected root {root!r} is not valid UTF-8"
            ) from error
        normalized.add(encoded.decode("utf-8"))
    return tuple(sorted(normalized, key=str.encode))


def _decode_git_name(raw_name: bytes, *, parent: str) -> str:
    try:
        return raw_name.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        location = f" under {parent!r}" if parent else ""
        raise BenchmarkIntegrityError(f"Protected Git path{location} is not valid UTF-8") from error


def _checkout_name(name: str, *, parent: str) -> str:
    try:
        return os.fsencode(name).decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        location = f" under {parent!r}" if parent else ""
        raise BenchmarkIntegrityError(
            f"Protected checkout path{location} is not valid UTF-8"
        ) from error


def _is_excluded(name: str) -> bool:
    return name in _EXCLUDED_DIRECTORY_NAMES or name in _EXCLUDED_FILE_NAMES


def _git_entry_at(tree: pygit2.Tree, root: str) -> pygit2.Object | None:
    current = tree
    entry: pygit2.Object | None = None
    components = root.split("/")
    for index, component in enumerate(components):
        component_bytes = component.encode("utf-8")
        entry = next((item for item in current if item.raw_name == component_bytes), None)
        if entry is None:
            return None
        if index < len(components) - 1:
            if not isinstance(entry, pygit2.Tree):
                return None
            current = entry
    return entry


def _collect_git_entry(
    entry: pygit2.Object,
    *,
    path: str,
    entries: dict[str, _ProtectedEntry],
) -> bool:
    mode = int(entry.filemode)
    name = path.rsplit("/", maxsplit=1)[-1]
    if _is_excluded(name):
        return False
    if isinstance(entry, pygit2.Tree):
        included = False
        for child in entry:
            child_name = _decode_git_name(child.raw_name, parent=path)
            child_path = f"{path}/{child_name}"
            included = _collect_git_entry(child, path=child_path, entries=entries) or included
        if included:
            entries[path] = _ProtectedEntry(
                path=path, kind="directory", mode=0o040000, content=b""
            )
        return included
    if not isinstance(entry, pygit2.Blob):
        raise BenchmarkIntegrityError(f"Unsupported protected Git object at {path!r}")
    if mode == int(pygit2.enums.FileMode.LINK):
        kind: ProtectedObjectKind = "symlink"
        normalized_mode = 0o120000
    elif mode in {
        int(pygit2.enums.FileMode.BLOB),
        int(pygit2.enums.FileMode.BLOB_EXECUTABLE),
    }:
        kind = "file"
        normalized_mode = 0o100755 if mode == int(pygit2.enums.FileMode.BLOB_EXECUTABLE) else 0o100644
    else:
        raise BenchmarkIntegrityError(f"Unsupported protected Git mode {mode:o} at {path!r}")
    entries[path] = _ProtectedEntry(
        path=path, kind=kind, mode=normalized_mode, content=bytes(entry.data)
    )
    return True


def _git_protected_tree(tree: pygit2.Tree, *, roots: tuple[str, ...]) -> _ProtectedTree:
    normalized_roots = _normalize_roots(roots)
    entries: dict[str, _ProtectedEntry] = {}
    for root in normalized_roots:
        entry = _git_entry_at(tree, root)
        if entry is not None:
            _collect_git_entry(entry, path=root, entries=entries)
    return _ProtectedTree(
        roots=normalized_roots,
        entries=tuple(entries[path] for path in sorted(entries, key=str.encode)),
    )


def _collect_checkout_path(
    path: Path,
    *,
    relative_path: str,
    entries: dict[str, _ProtectedEntry],
) -> bool:
    path_stat = path.lstat()
    name = relative_path.rsplit("/", maxsplit=1)[-1]
    if _is_excluded(name):
        return False
    if stat.S_ISLNK(path_stat.st_mode):
        entries[relative_path] = _ProtectedEntry(
            path=relative_path,
            kind="symlink",
            mode=0o120000,
            content=os.fsencode(path.readlink()),
        )
        return True
    if stat.S_ISREG(path_stat.st_mode):
        entries[relative_path] = _ProtectedEntry(
            path=relative_path,
            kind="file",
            mode=0o100755 if path_stat.st_mode & 0o111 else 0o100644,
            content=path.read_bytes(),
        )
        return True
    if stat.S_ISDIR(path_stat.st_mode):
        included = False
        with os.scandir(path) as children:
            for child in children:
                child_name = _checkout_name(child.name, parent=relative_path)
                child_relative_path = f"{relative_path}/{child_name}"
                included = (
                    _collect_checkout_path(
                        Path(child.path), relative_path=child_relative_path, entries=entries
                    )
                    or included
                )
        if included:
            entries[relative_path] = _ProtectedEntry(
                path=relative_path, kind="directory", mode=0o040000, content=b""
            )
        return included
    raise BenchmarkIntegrityError(f"Unsupported protected checkout object at {relative_path!r}")


def _checkout_root(repository_root: Path, root: str) -> Path | None:
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


def _checkout_protected_tree(
    repository_root: Path, *, roots: tuple[str, ...]
) -> _ProtectedTree:
    normalized_roots = _normalize_roots(roots)
    entries: dict[str, _ProtectedEntry] = {}
    for root in normalized_roots:
        root_path = _checkout_root(repository_root, root)
        if root_path is not None:
            _collect_checkout_path(root_path, relative_path=root, entries=entries)
    return _ProtectedTree(
        roots=normalized_roots,
        entries=tuple(entries[path] for path in sorted(entries, key=str.encode)),
    )


def _changed_protected_paths(
    release: _ProtectedTree, checkout: _ProtectedTree
) -> tuple[str, ...]:
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
