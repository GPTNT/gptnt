from __future__ import annotations

from rich.console import Console

from gptnt.cli.manual._output import ProgressRenderer, describe_profile, short_path
from gptnt.cli.manual._selection import SuitesOption, select_manual_requirements
from gptnt.common.logger import create_progress
from gptnt.common.paths import Paths
from gptnt.ktane.manuals.artifacts import compile_manual_artifacts
from gptnt.ktane.manuals.download import download_manual_assets
from gptnt.ktane.manuals.sources import ManualSources

console = Console()
paths = Paths()


async def compile_manuals(*, suites: SuitesOption = None) -> None:
    """Download, resolve, and compile the selected suite manuals."""
    selection = select_manual_requirements(suites=suites, paths=paths)
    sources = ManualSources.from_path(paths.manual_sources)

    console.print(f"Preparing [green]{selection.description}[/green]:")
    for suite in selection.suites:
        profile = describe_profile(
            suite.requirement.profile, path=suite.profile_path, root=paths.root
        )
        console.print(
            f"  [cyan]{suite.suite_name}[/cyan] → {profile} (seed {suite.requirement.rule_seed})"
        )

    console.print("Checking manual source cache and downloading missing assets…")
    with create_progress() as progress:
        _ = await download_manual_assets(
            [requirement.profile for requirement in selection.requirements],
            sources=sources,
            cache_dir=paths.manual_cache,
            root_dir=paths.root,
            progress=ProgressRenderer(progress),
        )

    with console.status("Compiling manual artifacts…"):
        artifacts = await compile_manual_artifacts(
            selection.requirements,
            sources=sources,
            cache_dir=paths.manual_cache,
            root_dir=paths.root,
        )

    console.print("Compiled manual artifacts:")
    for suite in selection.suites:
        artifact = artifacts[suite.requirement]
        console.print(
            f"  [cyan]{suite.suite_name}[/cyan] → {short_path(artifact.path, root=paths.root)}"
        )
