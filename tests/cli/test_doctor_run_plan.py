"""Tests for the `gptnt doctor <run.yaml>` run-plan cross-check.

The cross-check (`run_plan.analyze_run_plan`) is the focus: given a config-name → player_name
mapping (built here exactly as `check_models` hands one back) it dry-runs real, offline experiment
generation and reports coverage / count / resume findings. Generation runs through Hydra (offline,
deterministic), so these tests exercise the genuine
config→player_name resolution. The test player configs deliberately use a config name that differs
from its player_name (`test_defuser` → `test-defuser`), which is exactly the mismatch the cross-
check exists to resolve.

WandB is never contacted: the manifests default to `source: local`, so the resume row reads
completion from disk (an empty output dir here) and reports everything as still-to-run.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from gptnt.cli.doctor.run_plan import analyze_run_plan
from gptnt.cli.run.manifest import RunManifest

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.cli.doctor.checks import CheckResult


@pytest.fixture(autouse=True)
def empty_recorder_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the local resume scan at a guaranteed-empty dir so 'nothing done yet' is hermetic."""
    monkeypatch.setenv("EXPERIMENT_RECORDER_OUTPUTS", str(tmp_path / "__no_outputs__"))


def _manifest(**overrides: object) -> RunManifest:
    """A minimal valid manifest (wandb off) with per-test overrides merged in."""
    payload: dict[str, object] = {
        "suites": ["single-pairwise-sync"],
        "rooms": 2,
        "players": [{"player": "test_defuser"}, {"player": "test_expert"}],
    }
    payload.update(overrides)
    return RunManifest.model_validate(payload)


def _row(findings: list[CheckResult], name: str) -> CheckResult | None:
    return next((finding for finding in findings if finding.name == name), None)


def _coverage_spec_count(findings: list[CheckResult]) -> int:
    row = _row(findings, "Roster coverage")
    assert row is not None
    assert row.status == "pass", "expected a passing coverage summary"
    match = re.search(r"cover (\d+) spec", row.detail)
    assert match is not None
    return int(match.group(1))


def test_clean_roster_resolves_config_to_player_name_and_passes() -> None:
    """`test_defuser`/`test_expert` configs resolve to `test-defuser`/`test-expert`; pairwise
    covers."""
    manifest = _manifest()
    config_to_player = {"test_defuser": "test-defuser", "test_expert": "test-expert"}

    findings = analyze_run_plan(manifest, config_to_player).findings

    assert not any(finding.status == "fail" for finding in findings)
    assert _coverage_spec_count(findings) > 0
    resume = _row(findings, "Resume")
    assert resume is not None
    assert resume.status == "pass"  # local source, empty output dir → nothing done yet
    assert "(local)" in resume.detail
    assert resume.detail.startswith("0 of ")


@pytest.mark.skip(
    reason="no committed suite uses a with_best_* matchup; the anchor cross-check is dormant until "
    "baseline suites return (run-driven baselines, deferred)."
)
def test_anchor_not_in_roster_is_a_fatal_cross_check() -> None:
    """A `with_best_defuser` suite whose anchor isn't spawned would stall — that must be a ✗."""
    manifest = _manifest(
        suites=["single-best-defuser-sync"],
        players=[{"player": "test_defuser"}],
        anchors={"best_defuser": "test_expert"},  # resolves to test-expert, NOT in the roster
    )
    config_to_player = {"test_defuser": "test-defuser"}

    findings = analyze_run_plan(manifest, config_to_player).findings

    offender = _row(findings, "Player test-expert")
    assert offender is not None
    assert offender.status == "fail"
    assert "best_defuser" in offender.hint


def test_explicit_count_is_not_second_guessed() -> None:
    """`count` is the user's explicit choice, so a low count is reported in the plan, not
    failed."""
    manifest = _manifest(
        players=[{"player": "test_defuser", "count": 1}, {"player": "test_expert"}]
    )
    config_to_player = {"test_defuser": "test-defuser", "test_expert": "test-expert"}

    findings = analyze_run_plan(manifest, config_to_player).findings

    assert not any(finding.status == "fail" for finding in findings)
    assert _row(findings, "Count test_defuser") is None  # no insufficient-count check anymore
    coverage = _row(findings, "Roster coverage")
    assert coverage is not None
    assert "test_defuser=1" in coverage.detail  # the declared count appears in the spawn plan


def test_unresolved_roster_model_is_flagged_and_generation_continues() -> None:
    """A roster entry that didn't resolve to a player_name is ✗; the rest still cross-checks."""
    manifest = _manifest(
        rooms=1, players=[{"player": "test_defuser"}, {"player": "nonexistent_xyz"}]
    )
    config_to_player = {"test_defuser": "test-defuser", "nonexistent_xyz": None}

    findings = analyze_run_plan(manifest, config_to_player).findings

    unresolved = _row(findings, "Roster: nonexistent_xyz")
    assert unresolved is not None
    assert unresolved.status == "fail"


def test_multiple_suites_union_grows_the_spec_count() -> None:
    """`suites:` is a list: generation iterates per suite and unions, so more suites ⇒ more
    specs."""
    config_to_player = {"test_defuser": "test-defuser", "test_expert": "test-expert"}

    one = analyze_run_plan(_manifest(suites=["single-pairwise-sync"]), config_to_player).findings
    two = analyze_run_plan(
        _manifest(suites=["single-pairwise-sync", "single-parametric-sync"]), config_to_player
    ).findings

    assert _coverage_spec_count(two) > _coverage_spec_count(one)
