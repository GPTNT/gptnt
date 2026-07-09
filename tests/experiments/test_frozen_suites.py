"""A suite, and the missions it loads, are frozen once recorded in `configs/suites/suites.lock`.

`suites.lock` snapshots each `(name, revision)`: its `suite_digest`, the full config, and the
`mission_key`s it covers. A change to a suite config, or to any mission file it loads, changes the
digest, so `gptnt suite freeze --check` (mirrored by `test_lock_freezes_every_live_suite`) fails
until the suite's `revision` is bumped and the lock re-frozen. The provenance fields (`frozen_at`,
`git_sha`, `gptnt_version`) are deliberately ignored here, so a re-freeze that only restamps them
never churns this guard.

A separate check holds each suite's `name` to its filename, so a `suites=` reference and the
stamped `suite_name` stay in sync.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gptnt.cli.config_discovery import discover_suites
from gptnt.experiments.suite.compose import compose_suite
from gptnt.experiments.suite.freeze import FreezeReport, FreezeStamp
from gptnt.experiments.suite.lock import SuiteLock, default_lock_path

if TYPE_CHECKING:
    from gptnt.experiments.suite.core import Suite

# Provenance is stamped only onto newly appended entries, so any placeholder works: reconciling an
# already-complete lock appends nothing and never reads these.
_IGNORED_PROVENANCE = FreezeStamp(frozen_at="", gptnt_version="", git_sha="")


def _live_suites() -> list[Suite]:
    """Compose every suite exactly as generation does."""
    return [compose_suite(stem) for stem in discover_suites()]


def _committed_lock() -> SuiteLock:
    """The `suites.lock` checked into the tree."""
    return SuiteLock.from_lock_path(default_lock_path())


def test_lock_freezes_every_live_suite() -> None:
    """`gptnt suite freeze --check` passes: every live suite has a matching current-revision entry.

    A suite (or a mission it loads) changing without a `revision` bump makes an outcome `append`
    (missing entry) or `digest_mismatch`, failing this test.
    """
    outcomes = FreezeReport.reconcile(
        _live_suites(), _committed_lock(), _IGNORED_PROVENANCE
    ).outcomes
    assert [outcome.action for outcome in outcomes] == ["unchanged"] * len(outcomes)


def test_lock_entry_reconstructs_the_live_suite() -> None:
    """Each entry's stored config + missions rebuild a suite matching the live one.

    The reconstructed suite recomputes the SAME `suite_digest` and `mission_keys` as the live one,
    and the stored digest agrees. Compares only measured content; provenance is never read.
    """
    lock = _committed_lock()
    live_by_name = {suite.name: suite for suite in _live_suites()}
    for entry in lock.suites:
        rebuilt, missions = lock.load_suite(entry.name, entry.revision)
        live = live_by_name[entry.name]
        assert rebuilt.suite_digest == live.suite_digest == entry.suite_digest
        assert rebuilt.mission_keys == live.mission_keys == entry.mission_keys
        # missions resolve from the shared table, one per referenced key
        assert [mission.mission_key for mission in missions] == list(entry.mission_keys)


def test_lock_is_append_only_wellformed() -> None:
    """The lock is version 2, has no duplicate `(name, revision)`, and every key list is sorted."""
    lock = _committed_lock()
    assert lock.version == 2

    revisions = [(entry.name, entry.revision) for entry in lock.suites]
    assert len(revisions) == len(set(revisions))

    known_missions = set(lock.mission_specs())
    for entry in lock.suites:
        keys = list(entry.mission_keys)
        assert keys == sorted(set(keys))
        # every referenced mission is present in the shared table
        assert set(keys) <= known_missions


def test_suite_name_matches_filename() -> None:
    """Each suite's `name` must equal its config filename, so references can't drift."""
    mismatched = {
        stem: name for stem in discover_suites() if (name := compose_suite(stem).name) != stem
    }
    assert not mismatched, f"suite name != filename for: {mismatched}"
