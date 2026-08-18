"""Download the source assets required by configured manual profiles."""

from pathlib import Path
from typing import Annotated

import yaml
from cyclopts import Parameter
from rich.console import Console
from rich.filesize import decimal
from rich.progress import Progress, TaskID

from gptnt.cli.config_discovery import discover_suites
from gptnt.common.logger import create_progress
from gptnt.common.paths import Paths
from gptnt.experiments.suite.compose import compose_suite
from gptnt.ktane.manuals.download import DownloadProgress, download_manual_assets
from gptnt.ktane.manuals.profile import ManualProfile
from gptnt.ktane.manuals.sources import ManualSources

console = Console()
paths = Paths()

SuitesOption = Annotated[
    list[str] | None,
    Parameter(
        name="--suite",
        help="Download only the assets required by these configured suites (repeatable).",
    ),
]
AllProfilesOption = Annotated[
    bool,
    Parameter(
        name="--all-profiles",
        help="Download assets for every configured manual profile, including unused profiles.",
    ),
]


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
    if all_profiles and suites is not None:
        raise ValueError("--all-profiles cannot be combined with --suite")

    if all_profiles:
        selected_profiles, selection_description = _select_all_manual_profiles()
    else:
        selected_profiles, selection_description = _select_suite_manual_profiles(suites)

    profiles = list(dict.fromkeys(selected_profiles))

    console.print(
        f"Preparing [green]{selection_description}[/green] using "
        f"[green]{len(profiles)}[/green] distinct manual profile(s)."
    )
    sources = ManualSources.from_path(paths.manual_sources)
    with create_progress() as progress:
        download_summary = await download_manual_assets(
            profiles,
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


def _select_all_manual_profiles() -> tuple[list[ManualProfile], str]:
    profile_paths = sorted(
        profile_path
        for profile_path in paths.manual_profiles.glob("*.yaml")
        if not profile_path.stem.startswith("_")
    )
    if not profile_paths:
        raise ValueError("no configured manual profiles were found")
    return (
        [
            ManualProfile.model_validate(
                yaml.safe_load(profile_path.read_text(encoding="utf-8"))
            )
            for profile_path in profile_paths
        ],
        f"{len(profile_paths)} manual profile(s)",
    )


def _select_suite_manual_profiles(suites: SuitesOption) -> tuple[list[ManualProfile], str]:
    available_suites = discover_suites()
    suite_names = available_suites if suites is None else list(dict.fromkeys(suites))
    unknown_suites = sorted(set(suite_names) - set(available_suites))
    if unknown_suites:
        raise ValueError(f"unknown suites {unknown_suites}; available: {available_suites}")
    if not suite_names:
        raise ValueError("no suites were selected or configured")
    return (
        [compose_suite(suite_name).manual_profile for suite_name in suite_names],
        f"{len(suite_names)} suite(s)",
    )
