from __future__ import annotations

from rich.console import Console

from gptnt.cli.manual._selection import AllProfilesOption, SuitesOption, select_manual_profiles
from gptnt.common.paths import Paths
from gptnt.ktane.manuals.artifacts import prepare_manual_artifacts
from gptnt.ktane.manuals.sources import ManualSources

console = Console()
paths = Paths()


async def compile_manuals(
    *, suites: SuitesOption = None, all_profiles: AllProfilesOption = False
) -> None:
    """Download, resolve, and compile the selected default-rule manual profiles."""
    # Download and compile intentionally share selection semantics through this one boundary.
    selection = select_manual_profiles(suites=suites, all_profiles=all_profiles, paths=paths)
    sources = ManualSources.from_path(paths.manual_sources)

    artifacts = await prepare_manual_artifacts(
        selection.profiles, sources=sources, cache_dir=paths.manual_cache, root_dir=paths.root
    )
    for artifact in artifacts.values():
        console.print(artifact.path)
