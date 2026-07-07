from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, computed_field, model_validator
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
    truth and usage.
    """

    final_bomb_state: Annotated[BombState, AsJSON]
    usage: Annotated[dict[str, int], AsJSON]

    @classmethod
    def from_summary(
        cls, *, summary: ExperimentSummary, final_bomb_state: BombState, usage: dict[str, int]
    ) -> Self:
        """Extend an `ExperimentSummary` with its final bomb state and usage total."""
        return cls.model_validate(
            summary.model_dump() | {"final_bomb_state": final_bomb_state, "usage": usage}
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
    capabilities: list[SubmissionPlayer]

    provenance: ProvenanceMixin
    run_date: Instant


class InteractiveSubmission(SubmissionBase):
    """`submission.yaml` for an interactive suite."""

    suite: SuiteIdentity


class StaticsSubmission(SubmissionBase):
    """`submission.yaml` for a statics evaluation task."""

    dataset: DatasetIdentity
