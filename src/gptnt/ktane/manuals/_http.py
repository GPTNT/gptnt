"""HTTP streaming for manual asset downloads."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

import httpx

from gptnt.ktane.manuals._progress import ProgressReporter


@contextmanager
def _temporary_path(destination: Path) -> Iterator[Path]:
    """Keep partial downloads out of the cache until they are complete.

    Using temporary files is useful to make sure that we don't accidentally keep a partial
    download. However, the temporary file needs to exist after being closed so it can be moved to
    the final destination. If delete=True (the default), closing it deletes it before we can move
    it.

    We could copy it, but that would then duplicate the file and we don't wanna bother with that
    because that is unnecessary.
    """
    with NamedTemporaryFile(
        dir=destination.parent, prefix=f".{destination.name}.", delete=False
    ) as temporary:
        path = Path(temporary.name)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


async def download_to_cache(
    *,
    client: httpx.AsyncClient,
    url: str,
    destination: Path,
    progress_key: str,
    progress_description: str,
    reporter: ProgressReporter,
) -> int:
    """Stream one URL into the cache without exposing partial downloads."""
    # Make sure the destination exists
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Update the progress reporter that the task is starting
    reporter.update(progress_key, progress_description, completed=0)

    completed = 0

    with _temporary_path(destination) as temporary:
        async with client.stream("GET", url) as response:
            _ = response.raise_for_status()

            content_length = response.headers.get("Content-Length")
            total = int(content_length) if content_length else None

            with temporary.open("wb") as output:
                async for chunk in response.aiter_bytes():
                    _ = output.write(chunk)
                    completed += len(chunk)
                    reporter.update(
                        progress_key, progress_description, completed=completed, total=total
                    )

        _ = temporary.replace(destination)
    return completed
