from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class DownloadProgress:
    """One source-specific progress update."""

    key: str
    description: str
    completed: int | None = None
    total: int | None = None


type ProgressCallback = Callable[[DownloadProgress], None]


@dataclass
class ProgressReporter:
    """Send structured progress updates to an optional callback."""

    callback: ProgressCallback | None = None

    def update(
        self, key: str, description: str, *, completed: int | None = None, total: int | None = None
    ) -> None:
        """Report the current state of one keyed operation."""
        if self.callback is not None:
            self.callback(
                DownloadProgress(
                    key=key, description=description, completed=completed, total=total
                )
            )
