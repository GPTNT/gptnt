from pathlib import Path

from rich.progress import Progress, TaskID

from gptnt.ktane.manuals.profile import ManualProfile
from gptnt.ktane.manuals.progress import DownloadProgress


class ProgressRenderer:
    """Map source-keyed download events onto persistent Rich progress tasks."""

    def __init__(self, progress: Progress) -> None:
        """Store the Rich display and initialize its source-key-to-task mapping."""
        self.progress = progress
        self.tasks: dict[str, TaskID] = {}

    def __call__(self, update: DownloadProgress) -> None:
        """Create or update the persistent Rich task for one download source."""
        task_id = self.tasks.get(update.key)
        if task_id is None:
            task_id = self.progress.add_task(update.description, total=update.total)
            self.tasks[update.key] = task_id

        if update.completed is None:
            self.progress.update(task_id, description=update.description, total=update.total)
        else:
            self.progress.update(
                task_id,
                description=update.description,
                completed=update.completed,
                total=update.total,
            )


def short_path(path: Path, *, root: Path) -> str:
    """Render a complete path relative to the project when possible."""
    try:
        displayed = path.relative_to(root)
    except ValueError:
        displayed = path
    return displayed.as_posix()


def describe_profile(profile: ManualProfile, *, path: Path | None, root: Path) -> str:
    """Describe a configured profile path or identify an inline composed profile."""
    if path is not None:
        return short_path(path, root=root)
    return f"composed profile {profile.runtime_digest} ({len(profile.documents)} documents)"
