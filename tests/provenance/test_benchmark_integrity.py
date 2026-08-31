"""Behavioral tests for benchmark integrity and provenance capture."""

from __future__ import annotations

# pyright: reportUnusedCallResult=false, reportPrivateLocalImportUsage=false, reportMatchNotExhaustive=false
import os
import re
import subprocess
from pathlib import Path
from typing import Literal

import pygit2
import pytest

from gptnt.provenance import (
    BenchmarkIntegrityError,
    Provenance,
    check_benchmark_integrity,
    compute_release_protected_content_digest,
    gptnt_version,
    integrity as integrity_module,
)
from gptnt.provenance._protected_tree import (
    _ProtectedEntry,
    _ProtectedTree,
    build_checkout_protected_tree,
    build_git_protected_tree,
)
from gptnt.provenance.integrity import PROTECTED_PATHS_V1

_RELEASE_TAG = "v0.15.0"

type ChangeKind = Literal[
    "modified", "deleted", "file_mode", "untracked", "replaced", "permitted", "unrelated"
]
type UnsupportedRepositoryState = Literal["no_repository", "no_release_tag"]


def _tagged_repository(
    tmp_path: Path, *, reverse_creation_order: bool = False
) -> tuple[Path, str]:
    """Create a tagged repository containing each path-policy category."""
    repository = tmp_path / "repository"
    repository.parent.mkdir(parents=True, exist_ok=True)
    opened = pygit2.init_repository(repository)

    # Seed protected content, a permitted input, unrelated documentation, and an output ignore.
    files = {
        "src/gptnt/benchmark.py": "VALUE = 1\n",
        "configs/manual/sources.toml": "version = 1\n",
        "configs/player/custom.yaml": "model: example\n",
        "docs/notes.md": "notes\n",
        ".gitattributes": "* text=auto\n",
        ".gitignore": "output/\n",
    }
    entries = list(files.items())
    if reverse_creation_order:
        entries.reverse()
    for relative_path, content in entries:
        path = repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(content)

    index = opened.index
    index.add_all()
    index.write()
    signature = pygit2.Signature("Benchmark Test", "benchmark@example.com")
    release_commit = opened.create_commit(
        "HEAD", signature, signature, "release", index.write_tree(), []
    )
    # This commit and tag are the baseline for changes applied by each test.
    _ = opened.create_tag(
        _RELEASE_TAG,
        release_commit,
        pygit2.enums.ObjectType.COMMIT,
        signature,
        f"release {_RELEASE_TAG}",
    )
    # Simulate a platform where the checkout cannot represent Git executable bits.
    opened.config["core.filemode"] = False
    return repository, str(release_commit)


def _commit_file(repository: Path, relative_path: str, content: str) -> str:
    path = repository / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    discovered = pygit2.discover_repository(str(repository))
    assert discovered is not None
    opened = pygit2.Repository(discovered)
    opened.index.add(relative_path)
    opened.index.write()
    signature = pygit2.Signature("Benchmark Test", "benchmark@example.com")
    commit_id = opened.create_commit(
        "HEAD",
        signature,
        signature,
        relative_path,
        opened.index.write_tree(),
        [opened.head.target],
    )
    return str(commit_id)


def _annotated_tag(repository: Path, tag_name: str, commit_id: str | pygit2.Oid) -> None:
    discovered = pygit2.discover_repository(str(repository))
    assert discovered is not None
    opened = pygit2.Repository(discovered)
    signature = pygit2.Signature("Benchmark Test", "benchmark@example.com")
    _ = opened.create_tag(
        tag_name,
        pygit2.Oid(hex=commit_id) if isinstance(commit_id, str) else commit_id,
        pygit2.enums.ObjectType.COMMIT,
        signature,
        f"release {tag_name}",
    )


def _commit_from(opened: pygit2.Repository, parent: pygit2.Commit, *, message: str) -> pygit2.Oid:
    signature = pygit2.Signature("Benchmark Test", "benchmark@example.com")
    return opened.create_commit(None, signature, signature, message, parent.tree.id, [parent.id])


def test_unprotected_descendant_uses_newest_reachable_release(tmp_path: Path) -> None:
    repository, release_commit = _tagged_repository(tmp_path)
    _commit_file(repository, "docs/branch-notes.md", "branch notes\n")

    result = check_benchmark_integrity(repository)

    assert (result.release_tag, result.release_commit) == (_RELEASE_TAG, release_commit)
    assert result.protected_content_modified is False


def test_protected_descendant_is_compared_with_newest_reachable_release(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    _commit_file(repository, "src/gptnt/benchmark.py", "VALUE = 2\n")

    result = check_benchmark_integrity(repository)

    assert result.changed_protected_paths == ("src/gptnt/benchmark.py",)
    assert result.protected_content_modified is True


def test_newest_reachable_release_wins_over_older_release(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    newer_commit = _commit_file(repository, "docs/release.md", "new release\n")
    _annotated_tag(repository, "v0.16.0", newer_commit)
    _commit_file(repository, "docs/branch.md", "branch\n")

    assert check_benchmark_integrity(repository).release_tag == "v0.16.0"


def test_newer_release_on_second_merge_parent_is_selected(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    discovered = pygit2.discover_repository(str(repository))
    assert discovered is not None
    opened = pygit2.Repository(discovered)
    base = opened.head.peel(pygit2.Commit)
    first_parent = _commit_from(opened, base, message="first parent")
    second_parent = _commit_from(opened, base, message="second parent")
    _annotated_tag(repository, "v0.16.0", second_parent)
    opened.head.set_target(first_parent)
    signature = pygit2.Signature("Benchmark Test", "benchmark@example.com")
    _ = opened.create_commit(
        "HEAD", signature, signature, "merge", base.tree.id, [first_parent, second_parent]
    )

    assert check_benchmark_integrity(repository).release_tag == "v0.16.0"


def test_older_release_on_second_merge_parent_does_not_move_baseline_back(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    discovered = pygit2.discover_repository(str(repository))
    assert discovered is not None
    opened = pygit2.Repository(discovered)
    base = opened.head.peel(pygit2.Commit)
    first_parent = _commit_from(opened, base, message="new release")
    second_parent = _commit_from(opened, base, message="old release")
    _annotated_tag(repository, "v0.16.0", first_parent)
    _annotated_tag(repository, "v0.14.0", second_parent)
    opened.head.set_target(first_parent)
    signature = pygit2.Signature("Benchmark Test", "benchmark@example.com")
    _ = opened.create_commit(
        "HEAD", signature, signature, "merge", base.tree.id, [first_parent, second_parent]
    )

    assert check_benchmark_integrity(repository).release_tag == "v0.16.0"


def test_unreachable_release_tag_is_not_a_baseline(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    discovered = pygit2.discover_repository(str(repository))
    assert discovered is not None
    opened = pygit2.Repository(discovered)
    base = opened.head.peel(pygit2.Commit)
    opened.references.delete(f"refs/tags/{_RELEASE_TAG}")
    side_commit = _commit_from(opened, base, message="side release")
    _annotated_tag(repository, "v0.16.0", side_commit)
    signature = pygit2.Signature("Benchmark Test", "benchmark@example.com")
    _ = opened.create_commit("HEAD", signature, signature, "main child", base.tree.id, [base.id])

    with pytest.raises(BenchmarkIntegrityError, match="no reachable annotated release tag"):
        _ = check_benchmark_integrity(repository)


def test_only_release_tree_is_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository, _ = _tagged_repository(tmp_path)
    integrity_module._release_protected_tree.cache_clear()
    release_builds = 0
    checkout_builds = 0
    original_release_builder = integrity_module.build_git_protected_tree
    original_checkout_builder = integrity_module.build_checkout_protected_tree

    def count_release_build(*args: object, **kwargs: object) -> _ProtectedTree:  # noqa: WPS430
        nonlocal release_builds  # noqa: WPS420
        release_builds += 1
        return original_release_builder(*args, **kwargs)

    def count_checkout_build(*args: object, **kwargs: object) -> _ProtectedTree:  # noqa: WPS430
        nonlocal checkout_builds  # noqa: WPS420
        checkout_builds += 1
        return original_checkout_builder(*args, **kwargs)

    monkeypatch.setattr(integrity_module, "build_git_protected_tree", count_release_build)
    monkeypatch.setattr(integrity_module, "build_checkout_protected_tree", count_checkout_build)

    first = check_benchmark_integrity(repository)
    (repository / "src/gptnt/benchmark.py").write_text("VALUE = 2\n")
    second = check_benchmark_integrity(repository)

    assert (release_builds, checkout_builds) == (1, 2)
    assert first.protected_content_modified is False
    assert second.protected_content_modified is True


def test_release_digest_requires_tag_and_commit_to_identify_same_release(tmp_path: Path) -> None:
    repository, release_commit = _tagged_repository(tmp_path)

    digest = compute_release_protected_content_digest(
        repository, release_tag=_RELEASE_TAG, release_commit=release_commit
    )

    assert digest == check_benchmark_integrity(repository).release_digest


def test_release_digest_rejects_tag_commit_disagreement(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)

    with pytest.raises(BenchmarkIntegrityError, match="does not target"):
        _ = compute_release_protected_content_digest(
            repository, release_tag=_RELEASE_TAG, release_commit="0" * 40
        )


def test_release_digest_requires_annotated_semantic_tag(tmp_path: Path) -> None:
    repository, release_commit = _tagged_repository(tmp_path)
    discovered = pygit2.discover_repository(str(repository))
    assert discovered is not None
    opened = pygit2.Repository(discovered)
    opened.references.create("refs/tags/v0.16.0", opened.head.target)

    with pytest.raises(BenchmarkIntegrityError, match="annotated"):
        _ = compute_release_protected_content_digest(
            repository, release_tag="v0.16.0", release_commit=release_commit
        )


def test_release_digest_rejects_missing_or_malformed_tag(tmp_path: Path) -> None:
    repository, release_commit = _tagged_repository(tmp_path)

    with pytest.raises(BenchmarkIntegrityError, match="semantic release tag"):
        _ = compute_release_protected_content_digest(
            repository, release_tag="v01.2.3", release_commit=release_commit
        )
    with pytest.raises(BenchmarkIntegrityError, match="does not exist"):
        _ = compute_release_protected_content_digest(
            repository, release_tag="v9.9.9", release_commit=release_commit
        )


def test_protected_digest_is_stable_across_creation_order(tmp_path: Path) -> None:
    first, _ = _tagged_repository(tmp_path / "first")
    second, _ = _tagged_repository(tmp_path / "second", reverse_creation_order=True)

    first_result = check_benchmark_integrity(first)
    second_result = check_benchmark_integrity(second)

    assert first_result.checkout_digest == second_result.checkout_digest
    assert first_result.checkout_digest.startswith("sha256:")
    assert first_result.release_digest == first_result.checkout_digest


def test_digest_v1_has_fixed_canonical_vector() -> None:
    tree = _ProtectedTree(
        roots=("pyproject.toml", "src/gptnt"),
        entries=(
            _ProtectedEntry(path="pyproject.toml", kind="file", content=b"[project]\n"),
            _ProtectedEntry(path="src/gptnt", kind="directory", content=b""),
            _ProtectedEntry(path="src/gptnt/link.py", kind="symlink", content=b"benchmark.py"),
        ),
    )

    assert tree.digest == "sha256:ab2daa73fbfc48aeaeb3c1a74b9dae25da286b13657d66ea5d2d52061e1908d9"


def test_digest_serializer_orders_roots_and_entries() -> None:
    first = _ProtectedEntry(path="a/first", kind="file", content=b"first")
    second = _ProtectedEntry(path="z/second", kind="file", content=b"second")

    ordered = _ProtectedTree(roots=("a", "z"), entries=(first, second))
    reversed_tree = _ProtectedTree(roots=("z", "a"), entries=(second, first))

    assert reversed_tree.digest == ordered.digest


@pytest.mark.parametrize("root", ["src/./gptnt", "src/../gptnt", "src/\0gptnt"])
def test_invalid_protected_root_is_rejected(tmp_path: Path, root: str) -> None:
    repository, _ = _tagged_repository(tmp_path)

    with pytest.raises(BenchmarkIntegrityError, match="normalized repository-relative"):
        _ = build_checkout_protected_tree(repository, roots=(root,))


def test_pycache_path_component_is_excluded_for_any_object_kind(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    cache_path = repository / "src/gptnt/__pycache__"
    cache_path.write_bytes(b"not a directory")

    result = check_benchmark_integrity(repository)

    assert result.changed_protected_paths == ()


def test_protected_digest_uses_content_but_not_platform_file_mode(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    baseline = check_benchmark_integrity(repository).checkout_digest
    protected = repository / "src/gptnt/benchmark.py"

    protected.write_text("VALUE = 2\n")
    content_digest = check_benchmark_integrity(repository).checkout_digest
    protected.write_text("VALUE = 1\n")
    protected.chmod(protected.stat().st_mode | 0o111)
    mode_digest = check_benchmark_integrity(repository).checkout_digest

    assert content_digest != baseline
    assert mode_digest == baseline


def test_checkout_digest_normalizes_utf8_crlf(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    protected = repository / "src/gptnt/benchmark.py"
    protected.write_bytes(b"VALUE = 1\r\n")

    result = check_benchmark_integrity(repository)

    assert result.release_digest == result.checkout_digest
    assert result.changed_protected_paths == ()


def test_checkout_digest_ignores_ambient_git_attributes(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    discovered = pygit2.discover_repository(str(repository))
    assert discovered is not None
    attributes = Path(discovered) / "info/attributes"
    attributes.parent.mkdir(parents=True, exist_ok=True)
    attributes.write_text("src/gptnt/benchmark.py -text\n")
    (repository / "src/gptnt/benchmark.py").write_bytes(b"VALUE = 1\r\n")

    result = check_benchmark_integrity(repository)

    assert result.release_digest == result.checkout_digest
    assert result.changed_protected_paths == ()


def test_fixed_protected_cache_exclusion_does_not_change_digest(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    baseline = check_benchmark_integrity(repository).checkout_digest
    cache = repository / "src/gptnt/__pycache__/benchmark.pyc"
    cache.parent.mkdir()
    cache.write_bytes(b"generated")

    result = check_benchmark_integrity(repository)

    assert result.checkout_digest == baseline
    assert result.changed_protected_paths == ()


def test_index_only_change_does_not_change_checkout_digest(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    baseline = check_benchmark_integrity(repository).checkout_digest
    protected = repository / "src/gptnt/benchmark.py"
    protected.write_text("VALUE = 2\n")
    discovered = pygit2.discover_repository(str(repository))
    assert discovered is not None
    opened = pygit2.Repository(discovered)
    opened.index.add("src/gptnt/benchmark.py")
    opened.index.write()
    protected.write_text("VALUE = 1\n")

    result = check_benchmark_integrity(repository)

    assert result.checkout_digest == baseline
    assert result.changed_protected_paths == ()


def test_release_and_checkout_builders_match_for_nested_tree(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    nested = repository / "src/gptnt/nested/deeper/value.txt"
    nested.parent.mkdir(parents=True)
    nested.write_text("nested\n")
    discovered = pygit2.discover_repository(str(repository))
    assert discovered is not None
    opened = pygit2.Repository(discovered)
    opened.index.add("src/gptnt/nested/deeper/value.txt")
    opened.index.write()
    signature = pygit2.Signature("Benchmark Test", "benchmark@example.com")
    commit_id = opened.create_commit(
        "HEAD", signature, signature, "nested", opened.index.write_tree(), [opened.head.target]
    )

    release = build_git_protected_tree(opened[commit_id].tree, roots=PROTECTED_PATHS_V1)
    checkout = build_checkout_protected_tree(repository, roots=PROTECTED_PATHS_V1)

    assert release.entries == checkout.entries
    assert release.digest == checkout.digest


def test_leaf_symlink_target_changes_protected_digest(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    link = repository / "src/gptnt/link.py"
    link.symlink_to("benchmark.py")
    discovered = pygit2.discover_repository(str(repository))
    assert discovered is not None
    opened = pygit2.Repository(discovered)
    opened.index.add("src/gptnt/link.py")
    opened.index.write()
    signature = pygit2.Signature("Benchmark Test", "benchmark@example.com")
    commit_id = opened.create_commit(
        "HEAD", signature, signature, "symlink", opened.index.write_tree(), [opened.head.target]
    )
    _ = opened.create_tag(
        "v0.16.0", commit_id, pygit2.enums.ObjectType.COMMIT, signature, "release v0.16.0"
    )
    baseline = check_benchmark_integrity(repository).checkout_digest

    link.unlink()
    link.symlink_to("other.py")
    result = check_benchmark_integrity(repository)

    assert result.checkout_digest != baseline
    assert result.changed_protected_paths == ("src/gptnt/link.py",)


def test_directory_symlink_is_hashed_without_following_target(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    protected = repository / "src/gptnt"
    external = tmp_path / "external"
    external.mkdir()
    (external / "benchmark.py").write_text("VALUE = 1\n")
    (protected / "benchmark.py").unlink()
    protected.rmdir()
    protected.symlink_to(external, target_is_directory=True)

    first = check_benchmark_integrity(repository)
    (external / "benchmark.py").write_text("VALUE = 999\n")
    second = check_benchmark_integrity(repository)

    assert "src/gptnt" in first.changed_protected_paths
    assert first.checkout_digest == second.checkout_digest


def test_root_policy_is_canonical_and_entries_are_deduplicated(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)

    single = build_checkout_protected_tree(repository, roots=("src/gptnt",))
    equivalent = build_checkout_protected_tree(
        repository, roots=("src/gptnt", "src//gptnt/", "src/gptnt")
    )
    overlapping = build_checkout_protected_tree(repository, roots=("src", "src/gptnt"))

    assert equivalent == single
    assert overlapping.digest != single.digest
    assert len({entry.path for entry in overlapping.entries}) == len(overlapping.entries)


def test_empty_and_excluded_roots_contribute_only_root_policy(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    empty = repository / "empty"
    empty.mkdir()
    excluded = repository / "excluded"
    (excluded / "__pycache__").mkdir(parents=True)
    (excluded / "__pycache__/value.pyc").write_bytes(b"cache")
    (excluded / ".DS_Store").write_bytes(b"metadata")

    tree = build_checkout_protected_tree(repository, roots=("empty", "excluded"))

    assert tree.roots == ("empty", "excluded")
    assert tree.entries == ()


def test_file_root_contributes_its_entry(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)

    tree = build_checkout_protected_tree(repository, roots=("configs/manual/sources.toml",))

    assert [(entry.path, entry.kind) for entry in tree.entries] == [
        ("configs/manual/sources.toml", "file")
    ]


@pytest.mark.parametrize("ignore_source", ["worktree", "repository", "configured"])
def test_git_ignore_sources_cannot_hide_protected_file(tmp_path: Path, ignore_source: str) -> None:
    repository, _ = _tagged_repository(tmp_path)
    protected = repository / "src/gptnt/ignored.py"
    protected.write_text("ignored = True\n")
    discovered = pygit2.discover_repository(str(repository))
    assert discovered is not None
    opened = pygit2.Repository(discovered)
    pattern = "src/gptnt/ignored.py\n"
    match ignore_source:
        case "worktree":
            (repository / ".gitignore").write_text(pattern)
        case "repository":
            info_exclude = repository / ".git/info/exclude"
            info_exclude.parent.mkdir(parents=True, exist_ok=True)
            info_exclude.write_text(pattern)
        case "configured":
            excludes = tmp_path / "global-excludes"
            excludes.write_text(pattern)
            opened.config["core.excludesFile"] = str(excludes)

    result = check_benchmark_integrity(repository)

    assert "src/gptnt/ignored.py" in result.changed_protected_paths


def test_sourceless_bytecode_outside_cache_is_protected(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    baseline = check_benchmark_integrity(repository).checkout_digest
    bytecode = repository / "src/gptnt/extra.pyc"
    bytecode.write_bytes(b"generated")

    result = check_benchmark_integrity(repository)

    assert result.checkout_digest != baseline
    assert result.changed_protected_paths == ("src/gptnt/extra.pyc",)


def test_checkout_path_that_is_not_utf8_is_rejected(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    raw_path = b"".join((os.fsencode(repository / "src/gptnt"), b"/invalid-\xff.py"))
    try:
        descriptor = os.open(raw_path, os.O_WRONLY | os.O_CREAT, 0o644)
    except OSError:
        pytest.skip("filesystem rejects non-UTF-8 filenames")
    else:
        os.close(descriptor)

    with pytest.raises(BenchmarkIntegrityError, match=r"checkout path.*UTF-8"):
        _ = check_benchmark_integrity(repository)


def test_git_path_that_is_not_utf8_is_rejected(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    discovered = pygit2.discover_repository(str(repository))
    assert discovered is not None
    opened = pygit2.Repository(discovered)

    def make_tree(record: bytes) -> pygit2.Oid:  # noqa: WPS430
        result = subprocess.run(
            ["git", "mktree", "-z"], cwd=repository, input=record, check=True, capture_output=True
        )
        return pygit2.Oid(hex=result.stdout.strip().decode("ascii"))

    blob_id = opened.create_blob(b"invalid")
    gptnt_tree_id = make_tree(
        b"".join((b"100644 blob ", str(blob_id).encode("ascii"), b"\tinvalid-\xff.py\0"))
    )
    src_tree_id = make_tree(
        b"".join((b"040000 tree ", str(gptnt_tree_id).encode("ascii"), b"\tgptnt\0"))
    )
    root_tree_id = make_tree(
        b"".join((b"040000 tree ", str(src_tree_id).encode("ascii"), b"\tsrc\0"))
    )

    with pytest.raises(BenchmarkIntegrityError, match=r"Git path.*UTF-8"):
        _ = build_git_protected_tree(opened[root_tree_id], roots=("src/gptnt",))


def test_tagged_repository_produces_integrity_and_provenance(tmp_path: Path) -> None:
    """Use the tagged baseline for both integrity reporting and provenance capture."""
    repository, release_commit = _tagged_repository(tmp_path)

    integrity = check_benchmark_integrity(repository)
    provenance = Provenance.capture(repository)

    assert (integrity.release_tag, integrity.release_commit) == (_RELEASE_TAG, release_commit)
    assert integrity.protected_content_modified is False
    assert provenance.model_dump() == {
        "gptnt_version": gptnt_version(),
        "release_commit": release_commit,
        "release_tag": _RELEASE_TAG,
        "release_protected_content_digest": integrity.release_digest,
        "protected_content_digest": integrity.checkout_digest,
        "protected_content_modified": False,
    }


def test_forced_capture_records_null_release_provenance(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)

    provenance = Provenance.capture(repository, force=True)

    assert provenance.model_dump() == {
        "gptnt_version": gptnt_version(),
        "release_commit": None,
        "release_tag": None,
        "release_protected_content_digest": None,
        "protected_content_digest": None,
        "protected_content_modified": None,
    }


def _apply_change(repository: Path, change: ChangeKind) -> None:
    """Apply one working-tree state from the path-policy table."""
    protected = repository / "src/gptnt/benchmark.py"
    match change:
        case "modified":
            _ = (repository / "configs/manual/sources.toml").write_text("version = 2\n")
        case "deleted":
            protected.unlink()
        case "file_mode":
            protected.chmod(protected.stat().st_mode | 0o111)
        case "untracked":
            _ = (repository / "src/gptnt/untracked.py").write_text("VALUE = 2\n")
        case "replaced":
            discovered = pygit2.discover_repository(str(repository))
            assert discovered is not None
            index = pygit2.Repository(discovered).index
            index.remove("src/gptnt/benchmark.py")
            index.write()
            _ = protected.write_text("VALUE = 2\n")
        case "permitted":
            _ = (repository / "configs/player/custom.yaml").write_text("model: changed\n")
        case "unrelated":
            _ = (repository / "docs/notes.md").write_text("changed\n")
            output = repository / "output/cache/data.bin"
            output.parent.mkdir(parents=True)
            _ = output.write_bytes(b"cache")


@pytest.mark.parametrize(
    ("change", "protected", "permitted", "modified"),
    [
        # Tracked protected-content states.
        ("modified", ("configs/manual/sources.toml",), (), True),
        ("deleted", ("src/gptnt", "src/gptnt/benchmark.py"), (), True),
        ("file_mode", (), (), False),
        # Cases with untracked paths or permitted input.
        ("untracked", ("src/gptnt/untracked.py",), (), True),
        ("replaced", ("src/gptnt/benchmark.py",), (), True),
        ("permitted", (), ("configs/player/custom.yaml",), False),
        ("unrelated", (), (), False),
    ],
)
def test_path_policy(
    tmp_path: Path,
    change: ChangeKind,
    protected: tuple[str, ...],
    permitted: tuple[str, ...],
    modified: bool,
) -> None:
    """Classify each Git state and derive modification from protected content."""
    repository, _ = _tagged_repository(tmp_path)
    _apply_change(repository, change)

    result = check_benchmark_integrity(repository)

    assert result.changed_protected_paths == protected
    assert result.changed_input_paths == permitted
    assert result.protected_content_modified is modified


@pytest.mark.parametrize(
    ("state", "condition"),
    [
        ("no_repository", "not a Git repository"),
        ("no_release_tag", "no reachable annotated release tag"),
    ],
)
def test_unsupported_git_state_reports_repository_and_condition(
    tmp_path: Path, state: UnsupportedRepositoryState, condition: str
) -> None:
    """Report the repository path and unsupported Git condition in each error."""
    # Construct only the repository state needed to reach each error policy.
    match state:
        case "no_repository":
            repository = tmp_path
        case "no_release_tag":
            repository, _ = _tagged_repository(tmp_path)
            discovered = pygit2.discover_repository(str(repository))
            assert discovered is not None
            opened = pygit2.Repository(discovered)
            opened.references.delete(f"refs/tags/{_RELEASE_TAG}")
            signature = pygit2.Signature("Benchmark Test", "benchmark@example.com")
            _ = opened.create_tag(
                "v01.2.3",
                opened.head.target,
                pygit2.enums.ObjectType.COMMIT,
                signature,
                "not a SemVer release",
            )

    expected = rf"{re.escape(str(repository))}.*{condition}"
    with pytest.raises(BenchmarkIntegrityError, match=expected):
        _ = check_benchmark_integrity(repository)
