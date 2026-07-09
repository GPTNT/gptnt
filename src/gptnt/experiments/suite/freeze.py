"""Append-only reconciliation that writes `suites.lock`.

Given the live suites and any existing lock, `FreezeReport.reconcile` decides per suite whether to
append a new entry, leave a matching one unchanged, or flag a digest change made without a
`revision` bump. It never mutates or removes an existing entry, and appends only the missions not
already in the shared table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Self

from gptnt.experiments.suite.lock import MissionEntry, SuiteLock, SuiteLockEntry

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gptnt.experiments.suite.core import Suite
    from gptnt.ktane.mission_spec import KtaneMissionSpec


@dataclass(frozen=True, kw_only=True)
class FreezeStamp:
    """The provenance stamped onto a newly frozen entry.

    Injected rather than read during reconciliation, so it stays deterministic and testable.
    """

    frozen_at: str
    gptnt_version: str
    git_sha: str = ""

    def build_entry(self, suite: Suite) -> SuiteLockEntry:
        """A new lock entry for `suite`, stamped with this run's provenance."""
        return SuiteLockEntry(
            name=suite.name,
            revision=suite.revision,
            suite_digest=suite.suite_digest,
            frozen_at=self.frozen_at,
            gptnt_version=self.gptnt_version,
            git_sha=self.git_sha,
            mission_keys=suite.mission_keys,
            config=suite.model_dump(mode="json", exclude_none=True, exclude={"config_digest"}),
        )


FreezeAction = Literal["append", "unchanged", "digest_mismatch", "duplicate_keys"]
"""What reconciliation found for one suite:

- `append`: no entry yet for its current revision — freeze writes one.
- `unchanged`: the current-revision entry matches its digest.
- `digest_mismatch`: the current-revision entry exists but its digest differs — the suite changed
  without a `revision` bump.
- `duplicate_keys`: two of the suite's missions share a `mission_key`.
"""

_BLOCKING_ACTIONS: frozenset[FreezeAction] = frozenset(("digest_mismatch", "duplicate_keys"))


@dataclass(frozen=True, kw_only=True)
class SuiteFreezeOutcome:
    """What reconciliation found for one suite, and why."""

    name: str
    revision: int
    action: FreezeAction
    detail: str

    @classmethod
    def for_suite(cls, suite: Suite, action: FreezeAction, detail: str) -> Self:
        """This outcome for `suite`, carrying its current name and revision."""
        return cls(name=suite.name, revision=suite.revision, action=action, detail=detail)


@dataclass(frozen=True, kw_only=True)
class FreezeReport:
    """The outcome per suite plus the lock that would result from writing the appends."""

    outcomes: tuple[SuiteFreezeOutcome, ...]
    updated_lock: SuiteLock

    @classmethod
    def reconcile(
        cls, suites: Sequence[Suite], existing: SuiteLock | None, stamp: FreezeStamp
    ) -> Self:
        """Compute each suite's freeze outcome and the append-only lock that results.

        A missing lock is treated as an empty one. Existing entries are never mutated or removed;
        only missions absent from the shared table are appended. A `mission_key` mapping to two
        different bodies is a freeze error (`ValueError`).
        """
        lock = existing or SuiteLock()
        outcomes: list[SuiteFreezeOutcome] = []
        new_entries: list[SuiteLockEntry] = []
        for suite in suites:
            outcome, entry = cls._reconcile_one(suite, lock, stamp)
            outcomes.append(outcome)
            if entry is not None:
                new_entries.append(entry)
        new_missions = cls._new_missions(suites, lock)
        return cls(outcomes=tuple(outcomes), updated_lock=lock.append(new_entries, new_missions))

    @property
    def has_blocking_errors(self) -> bool:
        """True if any suite changed without a revision bump or has colliding mission keys.

        These block a write regardless of `--check`: the lock never records a mismatched digest.
        """
        return any(outcome.action in _BLOCKING_ACTIONS for outcome in self.outcomes)

    @classmethod
    def _reconcile_one(
        cls, suite: Suite, lock: SuiteLock, stamp: FreezeStamp
    ) -> tuple[SuiteFreezeOutcome, SuiteLockEntry | None]:
        """One suite's outcome against the lock, plus any entry to append."""
        duplicate = cls._first_duplicate(suite.mission_keys)
        if duplicate is not None:
            detail = f"missions share mission_key {duplicate!r}"
            return SuiteFreezeOutcome.for_suite(suite, "duplicate_keys", detail), None

        entry = lock.entry_for(suite.name, suite.revision)
        if entry is None:
            detail = f"revision {suite.revision} not yet frozen"
            return SuiteFreezeOutcome.for_suite(suite, "append", detail), stamp.build_entry(suite)
        if entry.suite_digest != suite.suite_digest:
            was, now = entry.suite_digest[:8], suite.suite_digest[:8]
            detail = f"digest {was} → {now} without a revision bump"
            return SuiteFreezeOutcome.for_suite(suite, "digest_mismatch", detail), None
        detail = f"revision {suite.revision} frozen"
        return SuiteFreezeOutcome.for_suite(suite, "unchanged", detail), None

    @staticmethod
    def _new_missions(suites: Sequence[Suite], lock: SuiteLock) -> list[MissionEntry]:
        """The missions across every live suite that aren't already in the lock's shared table.

        A `mission_key` that maps to two different mission bodies — whether across live suites or
        against the existing table — is a freeze error.
        """
        known = lock.mission_specs()
        fresh: dict[str, KtaneMissionSpec] = {}
        for suite in suites:
            for mission in suite.loaded_missions:
                key = mission.mission_key
                prior = fresh.get(key, known.get(key))
                if prior is not None and prior != mission:
                    raise ValueError(f"mission_key {key!r} maps to two different missions")
                if key not in known:
                    fresh[key] = mission
        return [MissionEntry(mission_key=key, spec=fresh[key]) for key in sorted(fresh)]

    @staticmethod
    def _first_duplicate(keys: tuple[str, ...]) -> str | None:
        """The first key that appears more than once, or `None` if all are unique."""
        seen: set[str] = set()
        for key in keys:
            if key in seen:
                return key
            seen.add(key)
        return None
