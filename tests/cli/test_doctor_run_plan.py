"""Tests for the `gptnt doctor <run.yaml>` run-plan cross-check.

The cross-check (`run_plan.analyze_run_plan`) is the focus: given a config-name → player_name
mapping (built here exactly as `check_players` hands one back) it dry-runs real, offline experiment
generation and reports coverage / count / resume findings. Generation runs through Hydra (offline,
deterministic), so these tests exercise the config→player_name resolution and the roster
cross-check.

WandB is never contacted: the manifests default to `source: local`, so the resume row reads
completion from disk (an empty output dir here) and reports everything as still-to-run.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from gptnt.cli.doctor import run_plan as run_plan_module
from gptnt.cli.doctor.run_plan import analyze_run_plan
from gptnt.cli.run.manifest import RunManifest

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.cli.checks.result import CheckResult


@pytest.fixture(autouse=True)
def empty_recorder_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the local resume scan at a guaranteed-empty dir so 'nothing done yet' is hermetic."""
    monkeypatch.setenv("EXPERIMENT_RECORDER_OUTPUTS", str(tmp_path / "__no_outputs__"))
    monkeypatch.setattr(
        run_plan_module, "load_manual_artifact", lambda *_args, **_kwargs: object()
    )


def _manifest(**overrides: object) -> RunManifest:
    """A minimal valid manifest (wandb off) with per-test overrides merged in."""
    payload: dict[str, object] = {
        "suites": ["single-pairwise-sync"],
        "rooms": 2,
        "players": [{"player": "test-defuser"}, {"player": "test-expert"}],
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
    """A clean pairwise roster resolves and covers."""
    manifest = _manifest()
    config_to_player = {"test-defuser": "test-defuser", "test-expert": "test-expert"}

    findings = analyze_run_plan(manifest, config_to_player).findings

    assert not any(finding.status == "fail" for finding in findings)
    assert _coverage_spec_count(findings) > 0
    resume = _row(findings, "Resume")
    assert resume is not None
    assert resume.status == "pass"  # local source, empty output dir → nothing done yet
    assert "(local)" in resume.detail
    assert resume.detail.startswith("0 of ")


def test_completed_specs_do_not_require_a_manual_artifact(monkeypatch: pytest.MonkeyPatch) -> None:
    """A no-op resumed run does not need manual files that no player will read."""

    def forbidden_load(*_args: object, **_kwargs: object) -> object:  # noqa: WPS430
        raise AssertionError("must not load")

    def no_remaining(*_args: object, **_kwargs: object) -> list[object]:  # noqa: WPS430
        return []

    manifest = _manifest()
    config_to_player = {"test-defuser": "test-defuser", "test-expert": "test-expert"}
    monkeypatch.setattr(run_plan_module, "filter_experiments", no_remaining)
    monkeypatch.setattr(run_plan_module, "load_manual_artifact", forbidden_load)

    result = analyze_run_plan(manifest, config_to_player)

    assert result.remaining_specs == []
    assert result.manual_artifacts == {}
    assert _row(result.findings, "Manual rule seed 1") is None


def test_loaded_specs_report_missing_manuals_when_the_roster_is_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run input still diagnoses its manuals when every roster config is broken."""
    valid_manifest = _manifest()
    valid_roster = {"test-defuser": "test-defuser", "test-expert": "test-expert"}
    specs = analyze_run_plan(valid_manifest, valid_roster).specs

    def missing_manual(*_args: object, **_kwargs: object) -> object:  # noqa: WPS430
        raise ValueError("manual is absent")

    monkeypatch.setattr(run_plan_module, "load_manual_artifact", missing_manual)
    result = analyze_run_plan(
        _manifest(players=[{"player": "nonexistent_xyz"}]), {"nonexistent_xyz": None}, specs=specs
    )

    manual = _row(result.findings, "Manual rule seed 1")
    assert manual is not None
    assert manual.status == "fail"


def test_explicit_count_is_not_second_guessed() -> None:
    """`count` is the user's explicit choice, so a low count is reported in the plan, not
    failed."""
    manifest = _manifest(
        players=[{"player": "test-defuser", "count": 1}, {"player": "test-expert"}]
    )
    config_to_player = {"test-defuser": "test-defuser", "test-expert": "test-expert"}

    findings = analyze_run_plan(manifest, config_to_player).findings

    assert not any(finding.status == "fail" for finding in findings)
    assert _row(findings, "Count test-defuser") is None  # no insufficient-count check anymore
    coverage = _row(findings, "Roster coverage")
    assert coverage is not None
    assert "test-defuser=1" in coverage.detail  # the declared count appears in the spawn plan


def test_unresolved_roster_model_is_flagged_and_generation_continues() -> None:
    """A roster entry that did not resolve to a player_name is ✗.

    The rest still cross-checks.
    """
    manifest = _manifest(
        rooms=1, players=[{"player": "test-defuser"}, {"player": "nonexistent_xyz"}]
    )
    config_to_player = {"test-defuser": "test-defuser", "nonexistent_xyz": None}

    findings = analyze_run_plan(manifest, config_to_player).findings

    unresolved = _row(findings, "Roster: nonexistent_xyz")
    assert unresolved is not None
    assert unresolved.status == "fail"


def test_multiple_suites_union_grows_the_spec_count() -> None:
    """`suites:` is a list: generation iterates per suite and unions, so more suites ⇒ more
    specs."""
    config_to_player = {"test-defuser": "test-defuser", "test-expert": "test-expert"}

    one = analyze_run_plan(_manifest(suites=["single-pairwise-sync"]), config_to_player).findings
    two = analyze_run_plan(
        _manifest(suites=["single-pairwise-sync", "single-parametric-sync"]), config_to_player
    ).findings

    assert _coverage_spec_count(two) > _coverage_spec_count(one)


def test_attempts_per_mission_multiplies_the_spec_count() -> None:
    """`attempts_per_mission` reaches generation via a Hydra override: N attempts give N specs."""
    config_to_player = {"test-defuser": "test-defuser", "test-expert": "test-expert"}

    once = analyze_run_plan(_manifest(attempts_per_mission=1), config_to_player).findings
    thrice = analyze_run_plan(_manifest(attempts_per_mission=3), config_to_player).findings

    assert _coverage_spec_count(thrice) == 3 * _coverage_spec_count(once)
    coverage = _row(thrice, "Roster coverage")
    assert coverage is not None
    assert "3 attempts/mission" in coverage.detail


def test_missing_compiled_manual_is_a_failed_run_plan_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctor blocks the run before it can start without the selected suite's manual."""
    config_to_player = {"test-defuser": "test-defuser", "test-expert": "test-expert"}

    def missing(*_args: object, **_kwargs: object) -> object:  # noqa: WPS430
        raise ValueError("manual artifact could not be read")

    monkeypatch.setattr(run_plan_module, "load_manual_artifact", missing, raising=False)
    findings = analyze_run_plan(_manifest(), config_to_player).findings

    manual = next(finding for finding in findings if finding.name.startswith("Manual"))
    assert manual.status == "fail"
    assert "manual compile --suite single-pairwise-sync" in manual.hint
