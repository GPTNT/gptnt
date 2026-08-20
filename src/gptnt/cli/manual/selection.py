"""Profile selection shared by manual download and compile commands."""

from dataclasses import dataclass
from typing import Annotated

import yaml
from cyclopts import Parameter

from gptnt.cli.config_discovery import discover_suites
from gptnt.common.paths import Paths
from gptnt.experiments.suite.compose import compose_suite
from gptnt.ktane.manuals.profile import ManualProfile

SuitesOption = Annotated[
    list[str] | None,
    Parameter(name="--suite", help="Select only these configured suites (repeatable)."),
]
AllProfilesOption = Annotated[
    bool,
    Parameter(
        name="--all-profiles",
        help="Select every configured manual profile, including profiles unused by suites.",
    ),
]


@dataclass(frozen=True, kw_only=True)
class ManualSelection:
    """Distinct profiles and the selection description shown by a command."""

    profiles: tuple[ManualProfile, ...]
    description: str


def _all_profiles(paths: Paths) -> tuple[list[ManualProfile], str]:
    """Load every public profile YAML in stable filename order."""
    # Underscore-prefixed YAML files are shared fragments, not independently selectable profiles.
    profile_paths = sorted(
        profile_path
        for profile_path in paths.manual_profiles.glob("*.yaml")
        if not profile_path.stem.startswith("_")
    )
    if not profile_paths:
        raise ValueError("no configured manual profiles were found")
    return (
        [
            ManualProfile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
            for path in profile_paths
        ],
        f"{len(profile_paths)} manual profile(s)",
    )


def _suite_profiles(suites: SuitesOption) -> tuple[list[ManualProfile], str]:
    """Compose the default or explicitly selected suites into their manual profiles."""
    available_suites = discover_suites()
    # dict preserves the user's first occurrence while dropping repeated suite flags.
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


def select_manual_profiles(
    *, suites: SuitesOption = None, all_profiles: AllProfilesOption = False, paths: Paths
) -> ManualSelection:
    """Select and deduplicate profiles using the commands' common flag semantics."""
    # These modes describe different universes of profiles and cannot be combined coherently.
    if all_profiles and suites is not None:
        raise ValueError("--all-profiles cannot be combined with --suite")
    profiles, description = _all_profiles(paths) if all_profiles else _suite_profiles(suites)
    # Multiple suites commonly share a profile; compile or download each distinct value once.
    return ManualSelection(profiles=tuple(dict.fromkeys(profiles)), description=description)
