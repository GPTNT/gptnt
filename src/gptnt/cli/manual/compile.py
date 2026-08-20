"""Compile source documents selected by configured manual profiles."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from anyio.to_thread import run_sync
from rich.console import Console

from gptnt.cli.manual.selection import AllProfilesOption, SuitesOption, select_manual_profiles
from gptnt.common.paths import Paths
from gptnt.ktane.manuals.compiler import compile_manual
from gptnt.ktane.manuals.download import download_manual_assets
from gptnt.ktane.manuals.preparation import prepare_compiler_sources
from gptnt.ktane.manuals.resolution import ResolvedOfficialDocument
from gptnt.ktane.manuals.resolve import resolve_manual_profile
from gptnt.ktane.manuals.sources import ManualSources

if TYPE_CHECKING:
    from gptnt.ktane.manuals.profile import ManualProfile

console = Console()
paths = Paths()

_DEFAULT_RULE_SEED = 1


def _profile_language(profile: ManualProfile, *, sources: ManualSources) -> str:
    if profile.include_frontmatter and sources.frontmatter:
        return sources.frontmatter[0].language
    return profile.documents[0].language


async def compile_manuals(
    *, suites: SuitesOption = None, all_profiles: AllProfilesOption = False
) -> None:
    """Download, resolve, and compile the selected default-rule manual profiles."""
    selection = select_manual_profiles(suites=suites, all_profiles=all_profiles, paths=paths)
    sources = ManualSources.from_path(paths.manual_sources)
    _ = await download_manual_assets(
        selection.profiles, sources=sources, cache_dir=paths.manual_cache, root_dir=paths.root
    )

    resolved_profiles = [
        resolve_manual_profile(
            profile,
            sources=sources,
            cache_dir=paths.manual_cache,
            root_dir=paths.root,
            language=_profile_language(profile, sources=sources),
            rule_seed=_DEFAULT_RULE_SEED,
        )
        for profile in selection.profiles
    ]

    if any(
        not isinstance(document, ResolvedOfficialDocument)
        for resolved in resolved_profiles
        for document in resolved
    ):
        await prepare_compiler_sources(paths.manual_cache)

    # Profiles compile sequentially so each artifact owns one Chromium process and output path.
    for resolved in resolved_profiles:
        artifact = await run_sync(  # noqa: WPS476
            functools.partial(compile_manual, resolved, cache_dir=paths.manual_cache)
        )
        console.print(artifact)
