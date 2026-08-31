from rich.console import Console
from rich.filesize import decimal

from gptnt.cli.manual._output import ProgressRenderer, describe_profile
from gptnt.cli.manual._selection import AllProfilesOption, SuitesOption, select_manual_profiles
from gptnt.common.logger import create_progress
from gptnt.common.paths import Paths
from gptnt.ktane.manuals.download import download_manual_assets
from gptnt.ktane.manuals.sources import ManualSources

console = Console()
paths = Paths()


async def download(
    *, suites: SuitesOption = None, all_profiles: AllProfilesOption = False
) -> None:
    """Download assets for configured suites, selected suites, or every manual profile."""
    # The compile command calls the same selector, keeping both commands' flags equivalent.
    selection = select_manual_profiles(suites=suites, all_profiles=all_profiles, paths=paths)

    console.print(
        f"Preparing [green]{selection.description}[/green] using "
        f"[green]{len(selection.profiles)}[/green] distinct manual profile(s)."
    )
    for suite in selection.suites:
        profile = describe_profile(suite.profile, path=suite.profile_path, root=paths.root)
        console.print(f"  [cyan]{suite.suite_name}[/cyan] → {profile}")
    sources = ManualSources.from_path(paths.manual_sources)
    # Rich owns display lifecycle while the downloader reports source-keyed progress events.
    with create_progress() as progress:
        download_summary = await download_manual_assets(
            selection.profiles,
            sources=sources,
            cache_dir=paths.manual_cache,
            root_dir=paths.root,
            progress=ProgressRenderer(progress),
        )

    # Report cache additions separately from hits so repeated preparation is visible to users.
    console.print(
        f"[green]Added[/green] {download_summary.added_files} files to the cache "
        f"({decimal(download_summary.added_bytes)}); "
        f"[cyan]cached[/cyan] {download_summary.cached_files} files "
        f"({decimal(download_summary.cached_bytes)})."
    )
    console.print(f"Manual cache: {download_summary.cache_dir}")
