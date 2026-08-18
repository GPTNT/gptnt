"""Integrity checks for the snapshots in `configs/suites/suites.lock`.

`suites.lock` snapshots each `(name, revision)`: its `suite_digest`, the full config, and the
`mission_key`s it covers. These tests check that the committed lock is internally consistent and
self-contained. They deliberately do not compare it with live suite files: requiring every suite
change to rewrite this shared registry creates avoidable merge conflicts. Run
`gptnt suite freeze --check` explicitly when live-to-lock parity needs checking.

A separate check holds each suite's `name` to its filename, so a `suites=` reference and the
stamped `suite_name` stay in sync.
"""

from __future__ import annotations

from gptnt.cli.config_discovery import discover_suites
from gptnt.experiments.suite.compose import compose_suite
from gptnt.experiments.suite.lock import SuiteLock, default_lock_path


def _committed_lock() -> SuiteLock:
    """The `suites.lock` checked into the tree."""
    return SuiteLock.from_lock_path(default_lock_path())


def test_lock_entry_reconstructs_the_frozen_suite() -> None:
    """Each entry's stored config and missions rebuild its frozen suite.

    The reconstructed suite recomputes the stored `suite_digest` and `mission_keys`. This checks
    snapshot integrity without coupling the lock to mutable live configs.
    """
    lock = _committed_lock()
    for entry in lock.suites:
        rebuilt, missions = lock.load_suite(entry.name, entry.revision)
        assert rebuilt.suite_digest == entry.suite_digest
        assert rebuilt.mission_keys == entry.mission_keys
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
