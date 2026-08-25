"""Release bundle contract tests."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pygit2

from gptnt.provenance import check_benchmark_integrity

_TAG = "v1.2.3"
_ASSET_NAMES = ("gptnt.tar.gz", "gptnt.tar.gz.sha256", "gptnt.zip", "gptnt.zip.sha256")
_BUILDER = Path(__file__).parents[2] / "scripts" / "build_release_bundle.py"


def _write(repository: Path, relative_path: str, content: str) -> None:
    path = repository / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content)


def _tagged_repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "source"
    opened = pygit2.init_repository(repository)
    _write(repository, "src/gptnt/history.py", "HISTORY = 1\n")
    index = opened.index
    index.add_all()
    index.write()
    signature = pygit2.Signature("Release Test", "release@example.com", 1_800_000_000, 0)
    parent = opened.create_commit("HEAD", signature, signature, "history", index.write_tree(), [])

    tracked_files = {
        ".gitattributes": "* text=auto\n",
        ".gitignore": ".env\noutput/\nstorage/keys/\n",
        "LICENSE": "release terms\n",
        "README.md": "# Fixture benchmark\n",
        "configs/manual/profile.yaml": "modules: []\n",
        "docs/release notes/file with spaces.txt": "included content\n",
        "scripts/example.py": "print('included')\n",
        "src/gptnt/benchmark.py": "VALUE = 1\n",
        "storage/keys/excluded.txt": "excluded content\n",
        "storage/ktane/mods/game.bin": "protected executable\n",
        "storage/prompts/system.txt": "protected prompt\n",
    }
    for relative_path, content in tracked_files.items():
        _write(repository, relative_path, content)
    (repository / "scripts/example.py").chmod(0o755)
    (repository / "storage/ktane/mods/game.bin").chmod(0o755)

    index.add_all()
    index.add("storage/keys/excluded.txt")
    index.write()
    commit = opened.create_commit(
        "HEAD", signature, signature, "release", index.write_tree(), [parent]
    )
    _ = opened.create_tag(
        _TAG, commit, pygit2.enums.ObjectType.COMMIT, signature, f"release {_TAG}"
    )

    _write(repository, "src/gptnt/untracked.py", "VALUE = 2\n")
    _write(repository, ".agents/private.txt", "unrelated agent data\n")
    return repository, str(commit)


def _build(
    repository: Path, tag: str, output_dir: Path, *, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - Execute this repository's builder without a shell.
        [
            sys.executable,
            os.fspath(_BUILDER),
            "--tag",
            tag,
            "--repository",
            os.fspath(repository),
            "--output-dir",
            os.fspath(output_dir),
        ],
        check=False,
        capture_output=True,
        env=os.environ | (environment or {}),
        text=True,
    )


def _extract_assets(output_dir: Path, destination: Path) -> tuple[Path, Path]:
    tar_destination = destination / "tar"
    zip_destination = destination / "zip"
    tar_destination.mkdir(parents=True)
    zip_destination.mkdir(parents=True)
    with tarfile.open(output_dir / "gptnt.tar.gz") as archive:
        assert {member.name.split("/", maxsplit=1)[0] for member in archive.getmembers()} == {
            "gptnt"
        }
        archive.extractall(tar_destination, filter="data")
    with zipfile.ZipFile(output_dir / "gptnt.zip") as archive:
        assert {name.split("/", maxsplit=1)[0] for name in archive.namelist()} == {"gptnt"}
        members = archive.infolist()
        archive.extractall(  # noqa: S202 - Extract the test-produced archive into a temp directory.
            zip_destination
        )
    # Python's ZIP extractor does not restore POSIX modes. Apply the modes stored in the archive.
    for member in members:
        (zip_destination / member.filename).chmod(member.external_attr >> 16 & 0o777)
    return tar_destination / "gptnt", zip_destination / "gptnt"


def _payload(repository: Path) -> tuple[set[str], dict[str, bytes]]:
    directories = set()
    files = {}
    for path in repository.rglob("*"):
        relative_path = path.relative_to(repository).as_posix()
        if path.is_dir():
            directories.add(relative_path)
        else:
            files[relative_path] = path.read_bytes()
    return directories, files


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - Inspect the temporary repository without a shell.
        ["git", "-C", os.fspath(repository), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def test_bundle_assets_are_deterministic_and_preserve_the_release_contract(tmp_path: Path) -> None:
    repository, release_commit = _tagged_repository(tmp_path)
    first_output = tmp_path / "first"
    second_output = tmp_path / "second"

    first_build = _build(repository, _TAG, first_output)
    second_build = _build(
        repository,
        _TAG,
        second_output,
        environment={
            "REPRO_TARFILE_DIR_MODE": "700",
            "REPRO_TARFILE_FILE_MODE": "600",
            "REPRO_TARFILE_GID": "123",
            "REPRO_TARFILE_GNAME": "ambient-group",
            "REPRO_TARFILE_UID": "123",
            "REPRO_TARFILE_UNAME": "ambient-user",
            "REPRO_ZIPFILE_DIR_MODE": "700",
            "REPRO_ZIPFILE_FILE_MODE": "600",
            "SOURCE_DATE_EPOCH": "1700000000",
        },
    )

    assert first_build.returncode == second_build.returncode == 0, (
        first_build.stderr,
        second_build.stderr,
    )
    assert {path.name for path in first_output.iterdir()} == set(_ASSET_NAMES)
    for asset_name in _ASSET_NAMES:
        assert (first_output / asset_name).read_bytes() == (
            second_output / asset_name
        ).read_bytes()
    for archive_name in ("gptnt.tar.gz", "gptnt.zip"):
        archive = first_output / archive_name
        with archive.open("rb") as archive_file:
            digest = hashlib.file_digest(archive_file, "sha256").hexdigest()
        assert (first_output / f"{archive_name}.sha256").read_text() == (
            f"{digest}  {archive_name}\n"
        )

    tar_repository, zip_repository = _extract_assets(first_output, tmp_path / "extracted")
    assert _payload(tar_repository) == _payload(zip_repository)
    for extracted in (tar_repository, zip_repository):
        assert (extracted / "docs/release notes/file with spaces.txt").read_text() == (
            "included content\n"
        )
        assert (extracted / "configs/manual/profile.yaml").is_file()
        assert (extracted / "storage/ktane/mods/game.bin").stat().st_mode & 0o111
        assert all(
            (extracted / name).is_file() for name in (".gitattributes", ".gitignore", "LICENSE")
        )
        assert not (extracted / "storage/keys").exists()
        assert not (extracted / "src/gptnt/untracked.py").exists()
        assert not (extracted / ".agents").exists()

        integrity = check_benchmark_integrity(extracted)
        assert (integrity.release_tag, integrity.release_commit) == (_TAG, release_commit)
        assert integrity.protected_content_modified is False

        assert _git(extracted, "rev-parse", "HEAD").stdout.strip() == release_commit
        assert _git(extracted, "rev-list", "--count", "HEAD").stdout.strip() == "1"
        assert _git(extracted, "rev-parse", "--is-shallow-repository").stdout.strip() == "true"
        assert _git(extracted, "remote").stdout == ""
        assert _git(extracted, "cat-file", "-t", f"refs/tags/{_TAG}").stdout.strip() == "tag"
        assert _git(extracted, "symbolic-ref", "-q", "HEAD").returncode != 0
        assert (extracted / ".git/index").is_file()
        assert (extracted / ".git/shallow").is_file()
        assert (extracted / f".git/refs/tags/{_TAG}").is_file()
        assert not (extracted / ".git/FETCH_HEAD").exists()
        assert not (extracted / ".git/logs").exists()
        assert not (extracted / ".git/description").exists()
        assert not list((extracted / ".git").rglob("*.sample"))
        assert os.fspath(repository) not in (extracted / ".git/config").read_text()


def test_nested_annotated_tag_produces_no_assets(tmp_path: Path) -> None:
    repository, _ = _tagged_repository(tmp_path)
    opened = pygit2.Repository(repository / ".git")
    inner_tag = opened.revparse_single(f"refs/tags/{_TAG}")
    assert isinstance(inner_tag, pygit2.Tag)
    signature = pygit2.Signature("Release Test", "release@example.com", 1_800_000_001, 0)
    _ = opened.create_tag(
        "v9.9.9", inner_tag.id, pygit2.enums.ObjectType.TAG, signature, "nested release tag"
    )
    output_dir = tmp_path / "assets"

    result = _build(repository, "v9.9.9", output_dir)

    assert result.returncode != 0
    assert "must point directly to a commit" in result.stderr
    assert not output_dir.exists()
