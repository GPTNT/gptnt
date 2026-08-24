from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from tomlkit import dumps, parse

from gptnt.common.paths import Paths
from gptnt.experiments.suite.definition import Suite
from gptnt.ktane.mission_spec import KtaneMissionSpec

LOCK_VERSION = 2
"""Schema version of the lock file itself, bumped only if this layout changes."""

LOCK_FILENAME = "suites.lock"

# TOML keys for the two array-of-tables, mapped to the model's plural fields in the I/O functions.
# One shared source so read and write cannot drift.
_MISSION_TABLE = "mission"
_SUITE_TABLE = "suite"


def default_lock_path() -> Path:
    """Return the canonical location of the lock, next to the suite configs it freezes."""
    return Paths().suite_configs / LOCK_FILENAME


class SuiteNotFrozenError(Exception):
    """A requested suite (or revision) has no entry in the lock."""


class MissionEntry(BaseModel):
    """One distinct mission, stored once and referenced by every suite that covers it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mission_key: str
    """Identity derived from both seeds and the sorted component names."""

    spec: KtaneMissionSpec

    @model_validator(mode="after")
    def check_mission_key(self) -> Self:
        """Require the table key to identify the stored mission body."""
        if self.mission_key != self.spec.mission_key:
            raise ValueError(
                f"mission entry key {self.mission_key!r} does not match stored mission "
                f"{self.spec.mission_key!r}"
            )
        return self


class SuiteLockEntry(BaseModel):
    """One frozen suite revision, with its digest, provenance, mission coverage, and config.

    `config` is `Suite.model_dump(mode="json", exclude_none=True)` (`config_digest` excluded), so
    `Suite.model_validate(config)` rebuilds the exact suite. `mission_keys` reference the shared
    `[[mission]]` table.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    revision: int = Field(ge=1)
    """Frozen comparability revision in the append-only sequence for this suite name."""

    suite_digest: str
    """Digest recomputed from the frozen suite configuration and referenced mission bodies."""

    frozen_at: str
    """ISO-8601 UTC instant the entry was first written."""

    gptnt_version: str
    """Installed GPTNT version used when this suite revision was frozen."""

    git_sha: str = ""
    """The commit the entry was frozen at, or `""` when git was unavailable."""

    mission_keys: tuple[str, ...]
    """Sorted `mission_key` of every mission the suite covers."""
    config: dict[str, Any]
    """JSON-form suite fields used to reconstruct the frozen suite, excluding `config_digest`."""

    @property
    def mission_set(self) -> str:
        """The mission-set name (the `missions_path` basename), as frozen in the config."""
        return Path(self.config["missions_path"]).name


def _validate_entry_snapshots(
    entries: tuple[SuiteLockEntry, ...], specs: dict[str, KtaneMissionSpec]
) -> None:
    """Verify each entry's identity and digest against its stored snapshot."""
    for entry in entries:
        suite = Suite.model_validate({"expert_protocol": None, **entry.config})
        if (entry.name, entry.revision) != (suite.name, suite.revision):
            raise ValueError(
                f"suite entry {entry.name!r} revision {entry.revision} does not match its "
                f"frozen config identity {suite.name!r} revision {suite.revision}"
            )
        missions = [specs[key] for key in entry.mission_keys]
        calculated_digest = suite.digest_for(missions)
        if calculated_digest != entry.suite_digest:
            raise ValueError(
                f"suite {entry.name!r} revision {entry.revision} digest does not match "
                "its frozen config and missions"
            )


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

    missions: tuple[MissionEntry, ...] = Field(default_factory=tuple, alias=_MISSION_TABLE)
    """Deduplicated mission bodies referenced by `mission_key` from frozen suites."""

    default_location: ClassVar[Path] = default_lock_path()

    @classmethod
    def from_lock_path(cls, path: Path | None = None) -> Self:
        """Load a lock from disk, or raise if the file is missing or malformed."""
        path = path or default_lock_path()
        if not path.exists():
            raise SuiteNotFrozenError(f"{path} not found; run `gptnt suite freeze` first")
        raw = parse(path.read_text())
        return cls.model_validate(raw.unwrap(), by_alias=True)

    def dump_to_path(self, path: Path) -> None:
        """Write the lock to disk as TOML."""
        _ = path.write_text(dumps(self.model_dump(mode="json", by_alias=True)))

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
        mission_keys = [mission.mission_key for mission in self.missions]
        if len(mission_keys) != len(set(mission_keys)):
            raise ValueError("duplicate mission_key in the mission table")

        revisions = [(entry.name, entry.revision) for entry in self.suites]
        if len(revisions) != len(set(revisions)):
            raise ValueError("duplicate (name, revision) in the suite entries")

        referenced = {key for entry in self.suites for key in entry.mission_keys}
        unknown = referenced - set(mission_keys)
        if unknown:
            raise ValueError(f"suites reference missions absent from the table: {unknown}")

        _validate_entry_snapshots(self.suites, self.mission_specs())
        return self

    def entry_for(self, name: str, revision: int) -> SuiteLockEntry | None:
        """Return the frozen entry for this `(name, revision)`, or `None` if not frozen."""
        for entry in self.suites:
            if entry.name == name and entry.revision == revision:
                return entry
        return None

    def mission_specs(self) -> dict[str, KtaneMissionSpec]:
        """Return the mission table as a `mission_key -> KtaneMissionSpec` lookup."""
        return {mission.mission_key: mission.spec for mission in self.missions}

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
        suite = Suite.model_validate({"expert_protocol": None, **entry.config})
        specs = self.mission_specs()
        missions = [specs[key] for key in entry.mission_keys]
        return suite, missions

    def snapshot(self, name: str, revision: int) -> Self:
        """Reduce this lock to one suite entry and exactly its referenced missions."""
        entry = self.select_entry(name, revision)
        mission_keys = set(entry.mission_keys)
        missions = tuple(
            mission for mission in self.missions if mission.mission_key in mission_keys
        )
        return self.model_validate({"suites": (entry,), "missions": missions})

    def append(self, new_entries: list[SuiteLockEntry], new_missions: list[MissionEntry]) -> Self:
        """Return a new lock with the entries and missions appended.

        The new entries must be for suites not already in the lock, and the new missions must be
        distinct from any existing mission_key. The result is sorted by `(name, revision)` for a
        stable file.
        """
        entries = sorted(
            (*self.suites, *new_entries), key=lambda entry: (entry.name, entry.revision)
        )
        missions = sorted((*self.missions, *new_missions), key=lambda mission: mission.mission_key)
        return self.model_validate(
            {**dict(self), "suites": tuple(entries), "missions": tuple(missions)}
        )
