"""Download the source assets required by configured manual profiles."""

from rich.console import Console
from rich.filesize import decimal
from rich.progress import Progress, TaskID

from gptnt.cli.manual.selection import AllProfilesOption, SuitesOption, select_manual_profiles
from gptnt.common.logger import create_progress
from gptnt.common.paths import Paths
from gptnt.ktane.manuals.download import DownloadProgress, download_manual_assets
from gptnt.ktane.manuals.sources import ManualSources

console = Console()
paths = Paths()


class _ProgressRenderer:
    """Map source-keyed download events onto persistent Rich progress tasks."""

    def __init__(self, progress: Progress) -> None:
        self.progress = progress
        self.tasks: dict[str, TaskID] = {}

    def __call__(self, update: DownloadProgress) -> None:
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


async def download(
    *, suites: SuitesOption = None, all_profiles: AllProfilesOption = False
) -> None:
    """Download assets for configured suites, selected suites, or every manual profile."""
    selection = select_manual_profiles(suites=suites, all_profiles=all_profiles, paths=paths)

    console.print(
        f"Preparing [green]{selection.description}[/green] using "
        f"[green]{len(selection.profiles)}[/green] distinct manual profile(s)."
    )
    sources = ManualSources.from_path(paths.manual_sources)
    with create_progress() as progress:
        download_summary = await download_manual_assets(
            selection.profiles,
            sources=sources,
            cache_dir=paths.manual_cache,
            root_dir=paths.root,
            progress=_ProgressRenderer(progress),
        )

    console.print(
        f"[green]Added[/green] {download_summary.added_files} files to the cache "
        f"({decimal(download_summary.added_bytes)}); "
        f"[cyan]cached[/cyan] {download_summary.cached_files} files "
        f"({decimal(download_summary.cached_bytes)})."
    )
    console.print(f"Manual cache: {download_summary.cache_dir}")
