"""Freeze semantics of the `suites.lock` registry: append-only reconciliation and TOML I/O."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from gptnt.experiments.suite.compose import compose_suite
from gptnt.experiments.suite.freeze import FreezeReport, FreezeStamp
from gptnt.experiments.suite.generate import generate_specs
from gptnt.experiments.suite.lock import MissionEntry, SuiteLock, SuiteNotFrozenError

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.experiments.suite.core import Suite

_STAMP = FreezeStamp(frozen_at="2026-01-01T00:00:00Z", gptnt_version="9.9.9", git_sha="cafef00d")


def _a_suite() -> Suite:
    """One real composed suite to reconcile against."""
    return compose_suite("single-solo-player-sync")


def test_reconcile_appends_a_new_suite() -> None:
    """A suite absent from the lock is appended with its digest, config, and provenance."""
    suite = _a_suite()
    report = FreezeReport.reconcile([suite], None, _STAMP)

    assert [outcome.action for outcome in report.outcomes] == ["append"]
    assert not report.has_blocking_errors

    assert len(report.updated_lock.suites) == 1
    entry = report.updated_lock.suites[0]
    assert entry.name == suite.name
    assert entry.suite_digest == suite.suite_digest
    assert entry.mission_keys == suite.mission_keys
    assert entry.config["matchup"]["pairing_type"] == suite.matchup.pairing_type
    assert (entry.frozen_at, entry.gptnt_version, entry.git_sha) == (
        _STAMP.frozen_at,
        _STAMP.gptnt_version,
        _STAMP.git_sha,
    )
    # every referenced mission is stored once in the shared table
    assert set(entry.mission_keys) == set(report.updated_lock.mission_specs())


def test_reconcile_is_unchanged_when_already_frozen() -> None:
    """Reconciling a suite against its own frozen entry appends nothing and reports unchanged."""
    suite = _a_suite()
    frozen = FreezeReport.reconcile([suite], None, _STAMP).updated_lock

    report = FreezeReport.reconcile([suite], frozen, _STAMP)
    assert [outcome.action for outcome in report.outcomes] == ["unchanged"]
    assert report.updated_lock.suites == frozen.suites


def test_reconcile_dedups_missions_shared_across_suites() -> None:
    """Two suites over the same mission set store each mission once, not twice."""
    pairwise = compose_suite("single-pairwise-sync")
    parametric = compose_suite("single-parametric-sync")
    assert pairwise.mission_keys == parametric.mission_keys  # both use single_module

    report = FreezeReport.reconcile([pairwise, parametric], None, _STAMP)
    stored = [mission.mission_key for mission in report.updated_lock.missions]
    assert stored == sorted(set(stored)) == sorted(pairwise.mission_keys)


def test_reconcile_requires_revision_bump_for_changed_content() -> None:
    """Changed suite content is blocked at one revision and accepted at the next revision."""
    suite = _a_suite()
    frozen = FreezeReport.reconcile([suite], None, _STAMP).updated_lock
    changed = suite.model_copy(update={"modality": ("audio", "language")})

    report = FreezeReport.reconcile([changed], frozen, _STAMP)
    assert [outcome.action for outcome in report.outcomes] == ["digest_mismatch"]
    assert report.has_blocking_errors
    assert report.updated_lock.suites == frozen.suites

    bumped = changed.model_copy(update={"revision": suite.revision + 1})
    bumped_report = FreezeReport.reconcile([bumped], frozen, _STAMP)
    assert [outcome.action for outcome in bumped_report.outcomes] == ["append"]
    assert bumped_report.updated_lock.suites[-1].suite_digest != frozen.suites[0].suite_digest


def test_load_suite_from_lock_rebuilds_suite_and_missions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stored config and mission table rebuild the suite without reading live missions."""
    suite = _a_suite()
    expected_digest = suite.suite_digest
    expected_mission_keys = suite.mission_keys
    lock = FreezeReport.reconcile([suite], None, _STAMP).updated_lock
    path = tmp_path / "suites.lock"
    lock.dump_to_path(path)
    monkeypatch.setattr(
        "gptnt.experiments.suite.core.load_missions",
        lambda _path: pytest.fail("lock loading read the live mission files"),
    )

    lock = SuiteLock.from_lock_path(path)
    rebuilt, missions = lock.load_suite(suite.name)
    assert rebuilt.digest_for(missions) == expected_digest
    assert rebuilt.expert_protocol is None  # a solo suite omits its expert (TOML has no null)
    assert [mission.mission_key for mission in missions] == list(expected_mission_keys)


def test_load_suite_from_lock_errors_when_unfrozen() -> None:
    """Selecting a suite (or revision) absent from the lock fails loudly."""
    lock = FreezeReport.reconcile([_a_suite()], None, _STAMP).updated_lock
    with pytest.raises(SuiteNotFrozenError, match="is not in the lock"):
        _ = lock.load_suite("never-frozen")
    with pytest.raises(SuiteNotFrozenError, match="revision 7"):
        _ = lock.load_suite("single-solo-player-sync", revision=7)


def test_lock_roundtrips_through_toml(tmp_path: Path) -> None:
    """A written lock reads back identically and rejects inconsistent frozen entries."""
    lock = FreezeReport.reconcile([_a_suite()], None, _STAMP).updated_lock
    path = tmp_path / "suites.lock"
    lock.dump_to_path(path)
    assert SuiteLock.from_lock_path(path) == lock

    entry = lock.suites[0]
    mismatched = entry.model_copy(
        update={"config": entry.config | {"revision": entry.revision + 1}}
    )
    with pytest.raises(ValidationError, match="does not match its frozen config identity"):
        _ = SuiteLock.model_validate({"suites": (mismatched,), "missions": lock.missions})

    wrong_digest = entry.model_copy(update={"suite_digest": "0" * 32})
    with pytest.raises(ValidationError, match="digest does not match"):
        _ = SuiteLock.model_validate({"suites": (wrong_digest,), "missions": lock.missions})

    mission = lock.missions[0]
    with pytest.raises(ValidationError, match="does not match stored mission"):
        _ = MissionEntry(mission_key="999999|Fake", spec=mission.spec)


def test_freeze_reload_and_generate_pins_suite_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The public freeze and generation path has one stable suite and experiment identity."""
    suite = _a_suite()
    lock = FreezeReport.reconcile([suite], None, _STAMP).updated_lock
    path = tmp_path / "suites.lock"
    lock.dump_to_path(path)
    monkeypatch.setattr("gptnt.experiments.suite.lock.default_lock_path", lambda: path)
    assert SuiteLock.from_lock_path() == lock

    experiments = generate_specs(["suites=single-solo-player-sync", "players.all=[test-defuser]"])
    experiment = experiments[0]

    assert (
        experiment.suite_name,
        experiment.suite_revision,
        experiment.suite_digest,
        experiment.fingerprint,
    ) == (
        "single-solo-player-sync",
        1,
        "c3eb87f851b818141f2decb4a9f5bf70",
        "e4a0c422f1e408ec81a610434270f647",
    )
