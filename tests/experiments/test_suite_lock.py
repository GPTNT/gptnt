"""Freeze semantics of the `suites.lock` registry: append-only reconciliation and TOML I/O."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from gptnt.experiments.suite.compose import compose_suite
from gptnt.experiments.suite.freeze import FreezeReport, FreezeStamp
from gptnt.experiments.suite.lock import SuiteLock, SuiteNotFrozenError

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


def test_reconcile_flags_digest_change_without_revision_bump() -> None:
    """A different digest at the same revision is a blocking mismatch, and nothing is appended."""
    suite = _a_suite()
    frozen = FreezeReport.reconcile([suite], None, _STAMP).updated_lock
    tampered = SuiteLock(
        version=frozen.version,
        missions=frozen.missions,
        suites=(frozen.suites[0].model_copy(update={"suite_digest": "0" * 32}),),
    )

    report = FreezeReport.reconcile([suite], tampered, _STAMP)
    assert [outcome.action for outcome in report.outcomes] == ["digest_mismatch"]
    assert report.has_blocking_errors
    assert report.updated_lock.suites == tampered.suites


def test_load_suite_from_lock_rebuilds_suite_and_missions() -> None:
    """The stored config + mission table rebuild a suite that recomputes the same digest."""
    suite = _a_suite()
    lock = FreezeReport.reconcile([suite], None, _STAMP).updated_lock

    rebuilt, missions = lock.load_suite(suite.name)
    assert rebuilt.suite_digest == suite.suite_digest
    assert rebuilt.expert_protocol is None  # a solo suite omits its expert (TOML has no null)
    assert [mission.mission_key for mission in missions] == list(suite.mission_keys)


def test_load_suite_from_lock_errors_when_unfrozen() -> None:
    """Selecting a suite (or revision) absent from the lock fails loudly."""
    lock = FreezeReport.reconcile([_a_suite()], None, _STAMP).updated_lock
    with pytest.raises(SuiteNotFrozenError, match="is not in the lock"):
        _ = lock.load_suite("never-frozen")
    with pytest.raises(SuiteNotFrozenError, match="revision 7"):
        _ = lock.load_suite("single-solo-player-sync", revision=7)


def test_lock_roundtrips_through_toml(tmp_path: Path) -> None:
    """A written lock reads back identical, mission table and array-of-tables and all."""
    lock = FreezeReport.reconcile([_a_suite()], None, _STAMP).updated_lock
    path = tmp_path / "suites.lock"
    lock.dump_to_path(path)
    assert SuiteLock.from_lock_path(path) == lock
