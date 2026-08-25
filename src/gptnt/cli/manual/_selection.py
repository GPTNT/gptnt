from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import yaml
from cyclopts import Parameter

from gptnt.cli.config_discovery import discover_suites
from gptnt.common.paths import Paths
from gptnt.experiments.suite.compose import compose_suite
from gptnt.ktane.manuals.profile import ManualProfile
from gptnt.ktane.manuals.requirement import ManualRequirement

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


@dataclass(frozen=True, kw_only=True)
class ManualRequirementSelection:
    """Distinct suite-owned manual requirements selected for compilation."""

    requirements: tuple[ManualRequirement, ...]
    description: str


def _load_all_manual_profiles(manual_profiles_root: Path) -> list[ManualProfile]:
    """Load every public profile YAML in stable filename order."""
    # Underscore-prefixed YAML files are shared fragments, not independently selectable profiles.
    profile_paths = sorted(
        profile_path
        for profile_path in manual_profiles_root.glob("*.yaml")
        if not profile_path.stem.startswith("_")
    )
    if not profile_paths:
        raise ValueError("no configured manual profiles were found")
    return [
        ManualProfile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in profile_paths
    ]


def _get_profiles_from_suites(suites: SuitesOption) -> list[ManualProfile]:
    """Compose the default or explicitly selected suites into their manual profiles."""
    available_suites = discover_suites()
    # dict preserves the user's first occurrence while dropping repeated suite flags.
    suite_names = available_suites if suites is None else list(dict.fromkeys(suites))

    unknown_suites = sorted(set(suite_names) - set(available_suites))

    if unknown_suites:
        raise ValueError(f"unknown suites {unknown_suites}; available: {available_suites}")
    if not suite_names:
        raise ValueError("no suites were selected or configured")

    return [compose_suite(suite_name).manual_profile for suite_name in suite_names]


def select_manual_profiles(
    *, suites: SuitesOption = None, all_profiles: AllProfilesOption = False, paths: Paths
) -> ManualSelection:
    """Select and deduplicate profiles using the commands' common flag semantics."""
    # These modes describe different universes of profiles and cannot be combined coherently.
    if all_profiles and suites is not None:
        raise ValueError("--all-profiles cannot be combined with --suite")

    if all_profiles:
        profiles = _load_all_manual_profiles(paths.manual_profiles)
    else:
        profiles = _get_profiles_from_suites(suites)

    # Multiple suites commonly share a profile. Compile or download each distinct value once.
    return ManualSelection(
        profiles=tuple(dict.fromkeys(profiles)), description=f"{len(profiles)} manual profile(s)"
    )


def select_manual_requirements(*, suites: SuitesOption = None) -> ManualRequirementSelection:
    """Select and deduplicate the profile-and-seed pairs owned by configured suites."""
    available_suites = discover_suites()
    suite_names = available_suites if suites is None else list(dict.fromkeys(suites))
    unknown_suites = sorted(set(suite_names) - set(available_suites))
    if unknown_suites:
        raise ValueError(f"unknown suites {unknown_suites}; available: {available_suites}")
    if not suite_names:
        raise ValueError("no suites were selected or configured")

    composed_suites = [compose_suite(suite_name) for suite_name in suite_names]
    requirements = tuple(
        ManualRequirement(profile=suite.manual_profile, rule_seed=suite.manual_rule_seed)
        for suite in composed_suites
    )

    return ManualRequirementSelection(
        requirements=tuple(dict.fromkeys(requirements)), description=f"{len(suite_names)} suite(s)"
    )
