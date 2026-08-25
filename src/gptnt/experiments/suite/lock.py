from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Self, override

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from tomlkit import dumps, parse

from gptnt.common.paths import Paths
from gptnt.experiments.suite.definition import Suite
from gptnt.ktane.mission_spec import KtaneMissionSpec

LOCK_VERSION = 3
"""The v3 TOML layout and suite-digest recipe contract."""

LOCK_FILENAME = "suites.lock"

# TOML keys for the two array-of-tables, mapped to the model's plural fields in the I/O functions.
# One shared source so read and write cannot drift.
_MISSION_TABLE = "mission"
_SUITE_TABLE = "suite"


def default_lock_path() -> Path:
    """Return the default lock location, next to the suite configurations it records."""
    return Paths().suite_configs / LOCK_FILENAME


class SuiteNotFrozenError(Exception):
    """A requested suite (or revision) has no entry in the lock."""


class MissionReference(BaseModel):
    """A readable reference from one suite revision to one stored mission body."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mission_key: str
    """Display label derived from the referenced mission body."""

    digest: str
    """Content identity derived from the referenced mission body."""


class SuiteLockEntry(Suite):
    """One frozen suite revision with configuration, missions, digest, and provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    suite_digest: str
    """Digest recomputed from the frozen suite configuration and referenced mission bodies."""

    frozen_at: str
    """ISO-8601 UTC instant the entry was first written."""

    gptnt_version: str
    """Installed GPTNT version used when this suite revision was frozen."""

    git_sha: str = ""
    """The commit the entry was frozen at, or `""` when git was unavailable."""

    missions: tuple[MissionReference, ...]
    """Readable references to missions that are included in this suite."""

    @property
    @override
    def digest(self) -> str:
        """Return the pre-computed digest for the suite."""
        return self.suite_digest

    @property
    @override
    def loaded_missions(self) -> list[KtaneMissionSpec]:
        """Reject authoring-file access; resolve persisted bodies through the lock instead."""
        raise RuntimeError(
            "SuiteLockEntry has no authoring-time mission bodies; call SuiteLock.load_suite()"
        )

    @property
    def mission_digests(self) -> tuple[str, ...]:
        """Return mission content identities for internal lookup compatibility."""
        return tuple(reference.digest for reference in self.missions)


def _validate_entry_snapshots(
    entries: tuple[SuiteLockEntry, ...], specs: dict[str, KtaneMissionSpec]
) -> None:
    """Verify each entry's digest against its stored mission bodies."""
    for entry in entries:
        _validate_entry_snapshot(entry, specs)


def _validate_entry_snapshot(entry: SuiteLockEntry, specs: dict[str, KtaneMissionSpec]) -> None:
    """Verify one entry's frozen identity and digest."""
    missions = []
    for reference in entry.missions:
        spec = specs[reference.digest]
        if reference.mission_key != spec.mission_key:
            raise ValueError(
                f"suite {entry.name!r} revision {entry.revision} references mission "
                f"{reference.digest} with a label that does not match its stored body"
            )
        missions.append(spec)
    _validate_entry_digest(entry, missions)


def _validate_entry_digest(entry: SuiteLockEntry, missions: list[KtaneMissionSpec]) -> None:
    """Require the stored digest to describe the entry's materialised content."""
    if entry.digest_for(missions) != entry.suite_digest:
        raise ValueError(
            f"suite {entry.name!r} revision {entry.revision} digest does not match "
            "its digest payload and missions"
        )


def _check_unique_mission_bodies(missions: tuple[KtaneMissionSpec, ...]) -> None:
    """Require each complete mission body to have one content digest."""
    if len({mission.digest for mission in missions}) != len(missions):
        raise ValueError("duplicate mission digest in the mission table")


def _check_unique_suite_revisions(entries: tuple[SuiteLockEntry, ...]) -> None:
    """Require each `(name, revision)` pair to appear once."""
    revisions = [(entry.name, entry.revision) for entry in entries]
    if len(revisions) != len(set(revisions)):
        raise ValueError("duplicate (name, revision) in the suite entries")


def _check_entry_references(
    entries: tuple[SuiteLockEntry, ...], bodies_by_digest: dict[str, KtaneMissionSpec]
) -> None:
    """Require references to resolve once and keep distinct labels within each suite."""
    referenced = {reference.digest for entry in entries for reference in entry.missions}
    unknown = referenced - set(bodies_by_digest)
    if unknown:
        raise ValueError(f"suites reference mission digests absent from the table: {unknown}")
    for entry in entries:
        _check_distinct_entry_references(entry)


def _check_distinct_entry_references(entry: SuiteLockEntry) -> None:
    """Require one reference per mission body and readable label in a suite revision."""
    digests = entry.mission_digests
    if len(digests) != len(set(digests)):
        raise ValueError(
            f"suite {entry.name!r} revision {entry.revision} repeats a mission digest"
        )
    keys = [reference.mission_key for reference in entry.missions]
    if len(keys) != len(set(keys)):
        raise ValueError(f"suite {entry.name!r} revision {entry.revision} repeats a mission key")


class SuiteLock(BaseModel):
    """A self-contained, append-only snapshot of all the frozen suites.

    We store the full suite config and the detailed mission specs in the lock file so that we can
    reconstruct a suite and its missions without reading the original configs.
    """

    model_config = ConfigDict(
        frozen=True, extra="forbid", validate_by_name=True, validate_by_alias=True
    )

    version: int = LOCK_VERSION

    suites: tuple[SuiteLockEntry, ...] = Field(default_factory=tuple, alias=_SUITE_TABLE)
    """Append-only frozen revisions for each suite."""

    missions: tuple[KtaneMissionSpec, ...] = Field(default_factory=tuple, alias=_MISSION_TABLE)
    """Deduplicated, complete mission bodies referenced by digest from frozen suites."""

    default_location: ClassVar[Path] = default_lock_path()

    @classmethod
    def from_lock_path(cls, path: Path | None = None) -> Self:
        """Load a lock from disk, or raise if the file is missing or malformed."""
        path = path or default_lock_path()
        if not path.exists():
            raise SuiteNotFrozenError(f"{path} not found; run `gptnt suite freeze` first")
        raw = parse(path.read_text())
        data = raw.unwrap()
        if "version" not in data:
            raise ValueError("suites.lock version is required")
        return cls.model_validate(data, by_alias=True)

    def dump_to_path(self, path: Path) -> None:
        """Write the lock to disk as TOML."""
        _ = path.write_text(dumps(self.model_dump(mode="json", by_alias=True, exclude_none=True)))

    @field_validator("version")
    @classmethod
    def check_lock_version(cls, version: int) -> int:
        """Verify the lock file's schema version is supported, or raise."""
        if version != LOCK_VERSION:
            raise ValueError(f"unsupported suites.lock version {version}; expected {LOCK_VERSION}")
        return version

    @model_validator(mode="after")
    def check_wellformed(self) -> Self:
        """Check uniqueness, references, and stored suite digests."""
        bodies_by_digest = self.mission_specs()
        _check_unique_mission_bodies(self.missions)
        _check_unique_suite_revisions(self.suites)
        _check_entry_references(self.suites, bodies_by_digest)
        _validate_entry_snapshots(self.suites, bodies_by_digest)
        return self

    def entry_for(self, name: str, revision: int) -> SuiteLockEntry | None:
        """Return the frozen entry for this `(name, revision)`, or `None` if not frozen."""
        for entry in self.suites:
            if entry.name == name and entry.revision == revision:
                return entry
        return None

    def mission_specs(self) -> dict[str, KtaneMissionSpec]:
        """Return the mission table as a `mission_digest -> KtaneMissionSpec` lookup."""
        return {mission.digest: mission for mission in self.missions}

    def mission_keys_for(self, entry: SuiteLockEntry) -> tuple[str, ...]:
        """Return readable mission keys for one frozen entry in its stored order."""
        return tuple(reference.mission_key for reference in entry.missions)

    def select_entry(self, name: str, revision: int | None) -> SuiteLockEntry:
        """Get the requested entry, or the latest revision when `revision` is None."""
        candidates = [entry for entry in self.suites if entry.name == name]
        if not candidates:
            raise SuiteNotFrozenError(
                f"suite {name!r} is not in the lock; run `gptnt suite freeze` first"
            )
        if revision is None:
            return max(candidates, key=lambda entry: entry.revision)
        entry = self.entry_for(name, revision)
        if entry is None:
            available = sorted(candidate.revision for candidate in candidates)
            raise SuiteNotFrozenError(
                f"suite {name!r} revision {revision} is not in the lock; frozen: {available}"
            )
        return entry

    def load_suite(
        self, name: str, revision: int | None = None
    ) -> tuple[Suite, list[KtaneMissionSpec]]:
        """Rebuild a frozen suite and its missions from this lock.

        `revision` defaults to the latest frozen revision of `name`. Raises `SuiteNotFrozenError`
        when the suite or the requested revision is absent.

        Note: A solo suite omits its expert. Since TOML has no null, a missing optional
        reconstructs as None.
        """
        entry = self.select_entry(name, revision)
        specs = self.mission_specs()
        missions = [specs[reference.digest] for reference in entry.missions]
        return entry, missions

    def snapshot(self, name: str, revision: int) -> Self:
        """Return the bundle suite snapshot for one frozen suite revision."""
        entry = self.select_entry(name, revision)
        mission_digests = set(entry.mission_digests)
        missions = tuple(mission for mission in self.missions if mission.digest in mission_digests)
        return self.model_validate({"suites": (entry,), "missions": missions})

    def append(
        self, new_entries: list[SuiteLockEntry], new_missions: list[KtaneMissionSpec]
    ) -> Self:
        """Return a new lock with the entries and missions appended.

        The new entries must not duplicate an existing `(name, revision)` pair. The new missions
        must be distinct from any existing mission digest. The result is sorted by `(name,
        revision)` for a stable file.
        """
        entries = sorted(
            (*self.suites, *new_entries), key=lambda entry: (entry.name, entry.revision)
        )
        missions = sorted((*self.missions, *new_missions), key=lambda mission: mission.digest)
        return self.model_validate(
            {**dict(self), "suites": tuple(entries), "missions": tuple(missions)}
        )
