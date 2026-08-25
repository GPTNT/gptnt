from __future__ import annotations

from rich.console import Console

from gptnt.cli.manual._selection import SuitesOption, select_manual_requirements
from gptnt.common.paths import Paths
from gptnt.ktane.manuals.artifacts import prepare_manual_artifacts
from gptnt.ktane.manuals.sources import ManualSources

console = Console()
paths = Paths()


async def compile_manuals(*, suites: SuitesOption = None) -> None:
    """Download, resolve, and compile the selected suite manuals."""
    selection = select_manual_requirements(suites=suites)
    sources = ManualSources.from_path(paths.manual_sources)

    artifacts = await prepare_manual_artifacts(
        selection.requirements, sources=sources, cache_dir=paths.manual_cache, root_dir=paths.root
    )
    for artifact in artifacts.values():
        console.print(artifact.path)
