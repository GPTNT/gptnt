"""Git operations used by the KtaneContent cache."""

import os
import shutil
import subprocess
from collections.abc import Sequence

import anyio
from anyio.to_thread import run_sync
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

_NETWORK_ATTEMPTS = 3


@retry(
    retry=retry_if_exception_type(subprocess.CalledProcessError),
    stop=stop_after_attempt(_NETWORK_ATTEMPTS),
    wait=wait_exponential(multiplier=0.5),
    reraise=True,
)
async def _run(
    arguments: Sequence[str], *, cwd: anyio.Path | None = None
) -> subprocess.CompletedProcess[bytes]:
    return await anyio.run_process(
        ["git", *arguments],
        cwd=cwd,
        env=dict(os.environ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


async def _clone(*, repository: str, destination: anyio.Path) -> None:
    # reset the clone destination
    if await destination.is_symlink() or await destination.is_file():
        _ = await destination.unlink()
    elif await destination.is_dir():
        await run_sync(shutil.rmtree, destination)

    # Make sure it exists
    _ = await destination.parent.mkdir(parents=True, exist_ok=True)

    _ = await _run(
        ["clone", "--filter=blob:none", "--no-checkout", "--depth=1", repository, str(destination)]
    )


async def _commit_is_present(repository_dir: anyio.Path, *, commit: str) -> bool:
    environment = dict(os.environ)
    environment["GIT_NO_LAZY_FETCH"] = "1"
    completed_process = await anyio.run_process(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=repository_dir,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed_process.returncode == 0


async def prepare_repository(*, repository: str, commit: str, destination: anyio.Path) -> None:
    """Create the cached clone and make the configured commit available."""
    if not await destination.joinpath(".git").is_dir():
        await _clone(repository=repository, destination=destination)

    # If the commit is present, then we don't need to do anything
    if await _commit_is_present(destination, commit=commit):
        return

    _ = await _run(
        ["fetch", "--filter=blob:none", "--depth=1", "--no-tags", "origin", commit],
        cwd=destination,
    )


async def restore(repository_dir: anyio.Path, *, commit: str, paths: Sequence[str]) -> None:
    """Materialize literal repository paths from one commit."""
    if paths:
        _ = await _run(
            [
                "restore",
                "--source",
                commit,
                "--worktree",
                "--",
                *(f":(literal){path}" for path in paths),
            ],
            cwd=repository_dir,
        )


async def tree_paths(repository_dir: anyio.Path, *, commit: str) -> set[str]:
    """Return all file paths tracked by one commit without materializing their contents."""
    tree = await _run(["ls-tree", "-rz", "--name-only", commit], cwd=repository_dir)
    return {path.decode("utf-8") for path in tree.stdout.split(b"\0") if path}
