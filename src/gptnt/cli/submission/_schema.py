from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator
from pydantic_ai import RunUsage
from whenever import Instant

from gptnt.experiments.db.schema import AsJSON
from gptnt.experiments.models import ExperimentSummary
from gptnt.experiments.provenance import ProvenanceMixin
from gptnt.experiments.suite import Suite
from gptnt.ktane.state.bomb import BombState
from gptnt.players.specification import PlayerCapabilities, PlayerIdentity, PlayerRole
from gptnt.statics.run_metadata import DatasetIdentity

SCHEMA_VERSION = 1


class Submitter(BaseModel):
    """Who is submitting.

    Written blank on build; the submitter fills these in and CI checks they are non-empty.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = ""

    contact: str = ""
    """@github handle or email."""

    affiliation: str | None = None


class SubmissionExperiment(ExperimentSummary):
    """One experiment in a submission.

    This is one row in the output bundle and made of the whole `ExperimentSummary` plus outcome
    truth and per-player usage.
    """

    final_bomb_state: Annotated[BombState, AsJSON]
    defuser_usage: Annotated[RunUsage, AsJSON]
    expert_usage: Annotated[RunUsage | None, AsJSON]

    @classmethod
    def from_summary(
        cls,
        *,
        summary: ExperimentSummary,
        final_bomb_state: BombState,
        usage_by_role: dict[PlayerRole, RunUsage],
    ) -> Self:
        """Extend an `ExperimentSummary` with its final bomb state and each player's usage."""
        return cls.model_validate(
            summary.model_dump()
            | {
                "final_bomb_state": final_bomb_state,
                "defuser_usage": usage_by_role["defuser"],
                "expert_usage": usage_by_role.get("expert"),
            }
        )


class SuiteIdentity(BaseModel):
    """The frozen suite the interactive results were measured against."""

    model_config = ConfigDict(extra="forbid")

    suite_name: str
    suite_revision: int
    suite_digest: str

    @classmethod
    def from_suite(cls, suite: Suite) -> Self:
        """Snapshot a `Suite`'s identity: its name, revision, and digest."""
        return cls(
            suite_name=suite.name, suite_revision=suite.revision, suite_digest=suite.suite_digest
        )


class SubmissionPlayer(BaseModel):
    """One player in a submission: its role, full capabilities, fingerprint, and attribution.

    `fingerprint` == `capabilities.fingerprint`, so it is a computed field and serialised into the
    manifest for readability. `identity` is the model's leaderboard from its player config.
    """

    model_config = ConfigDict(extra="forbid")

    role: PlayerRole
    capabilities: PlayerCapabilities
    identity: PlayerIdentity

    @computed_field
    @property
    def fingerprint(self) -> str:
        """The capability fingerprint, serialised alongside the entry."""
        return self.capabilities.fingerprint

    @model_validator(mode="before")
    @classmethod
    def _drop_serialised_fingerprint(cls, data: object) -> object:
        """Ignore a serialised `fingerprint` on input so a dumped manifest round-trips cleanly.

        Localised here, at the submission boundary that actually exports it — the core
        `PlayerCapabilities` stays a clean recorded model with no such machinery.
        """
        if isinstance(data, dict) and "fingerprint" in data:
            return {key: value for key, value in data.items() if key != "fingerprint"}  # noqa: WPS110
        return data


class SubmissionBase(BaseModel):
    """Fields shared by every `submission.yaml`."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    submission_id: str

    submitter: Submitter

    players: Annotated[list[SubmissionPlayer], Field(default_factory=list, min_length=1)]
    """Role-tagged model entries, defuser first."""

    provenance: ProvenanceMixin
    run_date: Instant

    @property
    def player(self) -> SubmissionPlayer:
        """The defuser player entry."""
        return self.players[0]

    @field_validator("players", mode="after")
    @classmethod
    def _only_one_defuser_player(cls, players: list[SubmissionPlayer]) -> list[SubmissionPlayer]:
        """There should only be one defuser player in a submission."""
        defuser_count = sum(player.role == "defuser" for player in players)
        if defuser_count != 1:
            raise ValueError(f"Expected exactly one defuser, got {defuser_count}")
        return players

    @field_validator("players", mode="after")
    @classmethod
    def _ensure_defuser_first(cls, players: list[SubmissionPlayer]) -> list[SubmissionPlayer]:
        """Ensure the defuser player is first in the list for consistency."""
        defuser_index = next(
            (idx for idx, player in enumerate(players) if player.role == "defuser"), None
        )
        if defuser_index is None:
            raise ValueError("Expected exactly one defuser, got 0")
        players.insert(0, players.pop(defuser_index))
        return players


class InteractiveSubmission(SubmissionBase):
    """`submission.yaml` for an interactive suite."""

    suite: SuiteIdentity


class StaticsSubmission(SubmissionBase):
    """`submission.yaml` for a statics evaluation task."""

    dataset: DatasetIdentity
