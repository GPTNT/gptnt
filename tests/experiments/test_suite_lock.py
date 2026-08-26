"""Freeze semantics of the `suites.lock` registry: append-only reconciliation and TOML I/O."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from gptnt.cli.config_discovery import discover_suites
from gptnt.experiments.recorder.parquet import KEY_FOOTER, RecordFooter, footer_from_player_record
from gptnt.experiments.records import ExperimentPlayerRecord, ExperimentSummary
from gptnt.experiments.suite.compose import compose_suite
from gptnt.experiments.suite.freeze import FreezeReport, FreezeStamp
from gptnt.experiments.suite.generate import generate_specs
from gptnt.experiments.suite.lock import MissionReference, SuiteLock, SuiteNotFrozenError

from tests._factories.experiments import (
    make_experiment_instance,
    make_provenance,
    make_solved_bomb,
)

if TYPE_CHECKING:
    from gptnt.experiments.suite.definition import Suite

_STAMP = FreezeStamp(frozen_at="2026-01-01T00:00:00Z", gptnt_version="9.9.9", git_sha="cafef00d")


def _a_suite() -> Suite:
    """One real composed suite to reconcile against."""
    return compose_suite("single-solo-player-sync")


def test_suite_digest_ignores_suite_identity_and_mission_path() -> None:
    """Suite naming and authoring locations do not change what a suite measures."""
    suite = _a_suite()
    relocated = suite.model_copy(
        update={"name": "renamed", "revision": 7, "missions_path": Path("other/missions")}
    )

    assert suite.digest_for(suite.loaded_missions) == relocated.digest_for(suite.loaded_missions)


def test_lock_entry_cannot_load_authoring_time_missions() -> None:
    """A persisted entry must be resolved through its enclosing lock snapshot."""
    entry = FreezeReport.reconcile([_a_suite()], None, _STAMP).updated_lock.suites[0]

    with pytest.raises(RuntimeError, match=r"SuiteLock\.load_suite"):
        _ = entry.loaded_missions


def test_reconcile_appends_a_new_suite() -> None:
    """A suite absent from the lock is appended with its digest, config, and provenance."""
    suite = _a_suite()
    report = FreezeReport.reconcile([suite], None, _STAMP)

    assert [outcome.action for outcome in report.outcomes] == ["append"]
    assert not report.has_blocking_errors

    assert len(report.updated_lock.suites) == 1
    entry = report.updated_lock.suites[0]
    assert entry.name == suite.name
    assert entry.suite_digest == suite.digest
    assert report.updated_lock.mission_keys_for(entry) == tuple(
        report.updated_lock.mission_specs()[reference.digest].mission_key
        for reference in entry.missions
    )
    assert entry.matchup.pairing_type == suite.matchup.pairing_type
    assert (entry.frozen_at, entry.gptnt_version, entry.git_sha) == (
        _STAMP.frozen_at,
        _STAMP.gptnt_version,
        _STAMP.git_sha,
    )
    # every referenced mission is stored once in the shared table
    assert set(entry.mission_digests) == set(report.updated_lock.mission_specs())


def test_reconcile_is_unchanged_when_already_frozen() -> None:
    """Reconciling a suite against its own frozen entry appends nothing and reports unchanged."""
    suite = _a_suite()
    frozen = FreezeReport.reconcile([suite], None, _STAMP).updated_lock

    report = FreezeReport.reconcile([suite], frozen, _STAMP)
    assert [outcome.action for outcome in report.outcomes] == ["unchanged"]
    assert report.updated_lock.suites == frozen.suites


def test_freeze_provenance_does_not_change_suite_digest() -> None:
    """Freeze bookkeeping does not affect the suite-content identity."""
    suite = _a_suite()
    earlier = FreezeReport.reconcile([suite], None, _STAMP).updated_lock.suites[0]
    later = FreezeReport.reconcile(
        [suite],
        None,
        FreezeStamp(frozen_at="2026-02-02T00:00:00Z", gptnt_version="10.0.0", git_sha="new"),
    ).updated_lock.suites[0]

    assert earlier.suite_digest == later.suite_digest


def test_reconcile_dedups_missions_shared_across_suites() -> None:
    """Suites over the same mission set store each mission once."""
    pairwise = compose_suite("single-pairwise-sync")
    parametric = compose_suite("single-parametric-sync")
    assert pairwise.mission_keys == parametric.mission_keys  # both use single_module

    report = FreezeReport.reconcile([pairwise, parametric], None, _STAMP)
    stored = [mission.digest for mission in report.updated_lock.missions]
    expected = sorted(mission.digest for mission in pairwise.loaded_missions)
    assert stored == sorted(set(stored)) == expected


def test_configured_suites_match_their_frozen_revision_and_rule_seed() -> None:
    """Each configured suite has a lock entry for its configured benchmark content."""
    expected_identities = {
        "multi-self-async": (2, 1764),
        "multi-self-sync": (2, 1764),
        "one-wires-sync": (1, 1),
        "single-pairwise-sync": (2, 1764),
        "single-parametric-sync": (2, 1764),
        "single-self-async": (2, 1764),
        "single-solo-player-sync": (2, 1764),
    }
    assert set(discover_suites()) == set(expected_identities)

    lock = SuiteLock.from_lock_path()
    for name, (revision, manual_rule_seed) in expected_identities.items():
        suite = compose_suite(name)
        entry = lock.entry_for(name, revision)
        assert (suite.revision, suite.manual_rule_seed) == (revision, manual_rule_seed)
        assert entry is not None
        assert entry.suite_digest == suite.digest


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
    expected_digest = suite.digest
    expected_mission_digests = {mission.digest for mission in suite.loaded_missions}
    lock = FreezeReport.reconcile([suite], None, _STAMP).updated_lock
    path = tmp_path / "suites.lock"
    lock.dump_to_path(path)
    monkeypatch.setattr(
        "gptnt.experiments.suite.definition.load_missions",
        lambda _path: pytest.fail("lock loading read the live mission files"),
    )

    lock = SuiteLock.from_lock_path(path)
    rebuilt, missions = lock.load_suite(suite.name)
    assert rebuilt.digest_for(missions) == expected_digest
    assert rebuilt.expert_protocol is None  # a solo suite omits its expert (TOML has no null)
    assert [mission.digest for mission in missions] == [
        reference.digest for reference in lock.suites[0].missions
    ]
    assert {mission.digest for mission in missions} == expected_mission_digests


def test_load_suite_from_lock_errors_when_unfrozen() -> None:
    """Selecting a suite (or revision) absent from the lock raises an error."""
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
    mismatched_reference = MissionReference(
        mission_key="wrong label", digest=entry.missions[0].digest
    )
    mismatched = entry.model_copy(update={"missions": (mismatched_reference, *entry.missions[1:])})
    with pytest.raises(ValidationError, match="label that does not match"):
        _ = SuiteLock.model_validate({"suites": (mismatched,), "missions": lock.missions})

    wrong_digest = entry.model_copy(update={"suite_digest": "0" * 32})
    with pytest.raises(ValidationError, match="digest does not match"):
        _ = SuiteLock.model_validate({"suites": (wrong_digest,), "missions": lock.missions})

    altered_body = lock.missions[0].model_copy(update={"time_limit": 1})
    with pytest.raises(ValidationError, match="absent from the table"):
        _ = SuiteLock.model_validate(
            {"suites": lock.suites, "missions": (altered_body, *lock.missions[1:])}
        )

    with pytest.raises(ValidationError, match="absent from the table"):
        _ = SuiteLock.model_validate({"suites": lock.suites, "missions": ()})


def test_freeze_reload_and_generate_pins_suite_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The public freeze, generation, object, and record path retains the manual profile."""
    suite = _a_suite()
    lock = FreezeReport.reconcile([suite], None, _STAMP).updated_lock
    path = tmp_path / "suites.lock"
    lock.dump_to_path(path)
    monkeypatch.setattr("gptnt.experiments.suite.lock.default_lock_path", lambda: path)
    loaded_lock = SuiteLock.from_lock_path()
    frozen_suite, _ = loaded_lock.load_suite(suite.name)
    assert loaded_lock == lock

    experiments = generate_specs(["suites=single-solo-player-sync", "players.all=[test-defuser]"])
    experiment = experiments[0]
    instance = make_experiment_instance(experiment)
    provenance = make_provenance()
    summary = ExperimentSummary.from_instance_and_bomb_state(
        instance=instance,
        final_bomb_state=make_solved_bomb(),
        is_hard_crash=False,
        provenance=provenance,
    )
    record = ExperimentPlayerRecord(
        experiment_instance=instance,
        player_content=instance.defuser,
        step_records=[],
        **provenance.model_dump(),
    )
    record_footer = RecordFooter.model_validate_json(footer_from_player_record(record)[KEY_FOOTER])

    assert (
        frozen_suite.manual_profile
        == experiment.manual_profile
        == instance.manual_profile
        == summary.manual_profile
        == record_footer.instance.manual_profile
    )

    assert (experiment.suite_name, experiment.suite_revision, experiment.suite_digest) == (
        suite.name,
        suite.revision,
        suite.digest,
    )


def test_generate_applies_the_frozen_suite_manual_rule_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Generation writes one suite-selected rule seed into every mission specification."""
    suite = _a_suite().model_copy(update={"manual_rule_seed": 7})
    lock = FreezeReport.reconcile([suite], None, _STAMP).updated_lock
    path = tmp_path / "suites.lock"
    lock.dump_to_path(path)
    monkeypatch.setattr("gptnt.experiments.suite.lock.default_lock_path", lambda: path)

    experiments = generate_specs(["suites=single-solo-player-sync", "players.all=[test-defuser]"])

    assert {experiment.mission_spec.rule_seed for experiment in experiments} == {7}
