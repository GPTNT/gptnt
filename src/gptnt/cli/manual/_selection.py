from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import yaml
from cyclopts import Parameter
from pydantic import ValidationError

from gptnt.cli.config_discovery import discover_suites
from gptnt.common.paths import Paths
from gptnt.experiments.suite.compose import compose_suite
from gptnt.experiments.suite.definition import Suite, SuiteSelector
from gptnt.experiments.suite.lock import SuiteLock
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
class SuiteProfile:
    """One suite's composed manual profile and its configured YAML path, when identifiable."""

    suite_name: str
    profile: ManualProfile
    profile_path: Path | None


@dataclass(frozen=True, kw_only=True)
class ManualSelection:
    """Distinct profiles, suite mappings, and the description shown by a command."""

    profiles: tuple[ManualProfile, ...]
    suites: tuple[SuiteProfile, ...]
    description: str


@dataclass(frozen=True, kw_only=True)
class ManualRequirementSelection:
    """Distinct suite-owned manual requirements selected for compilation."""

    requirements: tuple[ManualRequirement, ...]
    suites: tuple["SuiteManual", ...]
    description: str


@dataclass(frozen=True, kw_only=True)
class SuiteManual:
    """One suite's manual requirement and its configured profile path, when identifiable."""

    suite_name: str
    requirement: ManualRequirement
    profile_path: Path | None


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


def _find_profile_path(profile: ManualProfile, *, paths: Paths) -> Path | None:
    """Find the stable configured YAML path whose value matches a composed profile."""
    for profile_path in sorted(paths.manual_profiles.glob("*.yaml")):
        if profile_path.stem.startswith("_"):
            continue
        try:
            configured = ManualProfile.model_validate(
                yaml.safe_load(profile_path.read_text(encoding="utf-8"))
            )
        except (OSError, ValidationError, yaml.YAMLError):
            continue
        if configured == profile:
            return profile_path
    return None


def _resolve_selected_suites(suites: SuitesOption) -> dict[str, Suite]:
    """Resolve configured suite selectors to live or pinned suite definitions."""
    available_suites = discover_suites()

    # Parse each selector, preserve the first occurrence, then validate names against live config.
    suite_targets = available_suites if suites is None else suites
    parsed_selectors = [SuiteSelector.model_validate(target) for target in suite_targets]
    selectors = list({selector.target: selector for selector in parsed_selectors}.values())
    unknown_suites = sorted(
        selector.name for selector in selectors if selector.name not in available_suites
    )
    if unknown_suites:
        raise ValueError(f"unknown suites {unknown_suites}; available: {available_suites}")
    if not selectors:
        raise ValueError("no suites were selected or configured")

    lock: SuiteLock | None = None
    selected: dict[str, Suite] = {}

    # Unpinned selectors compose current config.
    # Pinned selectors load the exact frozen revision.
    for selector in selectors:
        if selector.revision is None:
            selected[selector.target] = compose_suite(selector.name)
            continue
        lock = lock or SuiteLock.from_lock_path()
        suite, _ = lock.load_suite(selector.name, selector.revision)
        selected[selector.target] = suite
    return selected


def select_manual_profiles(
    *, suites: SuitesOption = None, all_profiles: AllProfilesOption = False, paths: Paths
) -> ManualSelection:
    """Select and deduplicate profiles using the commands' common flag semantics."""
    # These modes describe different universes of profiles and cannot be combined coherently.
    if all_profiles and suites is not None:
        raise ValueError("--all-profiles cannot be combined with --suite")

    if all_profiles:
        profiles = _load_all_manual_profiles(paths.manual_profiles)
        suite_profiles: list[SuiteProfile] = []
        description = f"{len(profiles)} manual profile(s)"
    else:
        selected_suites = _resolve_selected_suites(suites)
        suite_profiles = [
            SuiteProfile(
                suite_name=target,
                profile=suite.manual_profile,
                profile_path=_find_profile_path(suite.manual_profile, paths=paths),
            )
            for target, suite in selected_suites.items()
        ]
        profiles = [suite.profile for suite in suite_profiles]
        description = f"{len(suite_profiles)} suite(s)"

    # Multiple suites commonly share a profile. Compile or download each distinct value once.
    return ManualSelection(
        profiles=tuple(dict.fromkeys(profiles)),
        suites=tuple(suite_profiles),
        description=description,
    )


def select_manual_requirements(
    *, suites: SuitesOption = None, paths: Paths
) -> ManualRequirementSelection:
    """Select and deduplicate the profile-and-seed pairs owned by configured suites."""
    selected_suites = _resolve_selected_suites(suites)
    suite_manuals = tuple(
        SuiteManual(
            suite_name=target,
            requirement=ManualRequirement(
                profile=suite.manual_profile, rule_seed=suite.manual_rule_seed
            ),
            profile_path=_find_profile_path(suite.manual_profile, paths=paths),
        )
        for target, suite in selected_suites.items()
    )

    return ManualRequirementSelection(
        requirements=tuple(dict.fromkeys(suite.requirement for suite in suite_manuals)),
        suites=suite_manuals,
        description=f"{len(suite_manuals)} suite(s)",
    )
