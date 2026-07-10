from typing import Annotated, Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_ai import RunUsage
from whenever import Instant

from gptnt.cli.config_discovery import player_identity
from gptnt.experiments.db.schema import AsJSON
from gptnt.experiments.models import ExperimentSummary
from gptnt.experiments.provenance import Provenance
from gptnt.experiments.suite.core import SuiteIdentity
from gptnt.ktane.state.bomb import BombState
from gptnt.players.specification import PlayerCapabilities, PlayerIdentity, PlayerRole
from gptnt.statics.run_metadata import StaticsIdentity

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


type SubmissionPairingKey = tuple[str, str, str]


def describe_pairing(defuser_name: str, expert_name: str | None, mission_key: str) -> str:
    """Human-readable label for a (defuser, expert, mission) pairing, for reporting."""
    return f"{defuser_name} + {expert_name or 'solo'} on {mission_key}"


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

    @property
    def pairing_key(self) -> SubmissionPairingKey:
        """(defuser fingerprint, expert fingerprint, mission key) tuple to identify this run."""
        return (
            self.defuser_capabilities.fingerprint,
            self.expert_capabilities.fingerprint if self.expert_capabilities else "",
            self.mission_key,
        )

    @property
    def pairing_description(self) -> str:
        """Human-readable description of the pairing, for reporting."""
        expert = self.expert_capabilities.player_name if self.expert_capabilities else None
        return describe_pairing(self.defuser_capabilities.player_name, expert, self.mission_key)


class SubmissionPlayer(BaseModel):
    """One player in a submission: its role, full capabilities, fingerprint, and attribution.

    `fingerprint` == `capabilities.fingerprint`, so it is a computed field and serialised into the
    manifest for readability. `identity` is the model's leaderboard from its player config.
    """

    model_config = ConfigDict(extra="forbid")

    role: PlayerRole
    capabilities: PlayerCapabilities
    identity: PlayerIdentity

    @classmethod
    def for_role(cls, role: PlayerRole, capabilities: PlayerCapabilities) -> Self:
        """Build a role-tagged entry, resolving the model's leaderboard `identity` from its config.

        A submission must be attributable, so a model with no `identity` block is a hard error.
        """
        identity = player_identity(capabilities.player_name)
        return cls(role=role, capabilities=capabilities, identity=identity)

    @computed_field
    @property
    def fingerprint(self) -> str:
        """The capability fingerprint, serialised alongside the entry."""
        return self.capabilities.fingerprint

    @model_validator(mode="wrap")
    @classmethod
    def _verify_serialised_fingerprint(
        cls,
        data: Any,
        handler: ModelWrapValidatorHandler[Self],  # noqa: WPS110
    ) -> Self:
        """Check a serialised `fingerprint` still matches its capabilities, then drop it.

        The written value is a computed field (display only), so a round-trip must discard it —
        but a manifest whose written fingerprint disagrees with its own `capabilities` has been
        tampered with (or built by different code) and must not parse. Localised here, at the
        submission boundary that actually exports it — the core `PlayerCapabilities` stays a clean
        recorded model with no such machinery.
        """
        written = None
        if isinstance(data, dict) and "fingerprint" in data:
            written = data["fingerprint"]
            data = {key: value for key, value in data.items() if key != "fingerprint"}  # noqa: WPS110
        player = handler(data)
        if written is not None and written != player.capabilities.fingerprint:
            raise ValueError(
                f"serialised fingerprint {written!r} does not match the one recomputed from "
                f"{player.capabilities.player_name!r}'s capabilities"
            )
        return player


class Submission[IdentityT: SuiteIdentity | StaticsIdentity](BaseModel):
    """One `submission.yaml`, parameterised by the identity of what was measured.

    The `measured` block is the discriminator: a `SuiteIdentity` makes it an interactive
    submission, a `StaticsIdentity` a statics one. Everything else is shared.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    submission_id: str

    measured: IdentityT
    """What was measured: a frozen suite, or a statics task with its dataset pin."""

    submitter: Submitter

    players: Annotated[list[SubmissionPlayer], Field(default_factory=list, min_length=1)]
    """Role-tagged model entries, defuser first."""

    provenance: Provenance
    run_date: Instant

    @property
    def player(self) -> SubmissionPlayer:
        """The defuser player entry."""
        return self.players[0]

    @property
    def target(self) -> str:
        """What was measured, with its pin — the bundle dir's leaf name."""
        return self.measured.target

    @field_validator("schema_version")
    @classmethod
    def _supported_schema_version(cls, version: int) -> int:
        """A manifest written by a different schema can't be reasoned about here."""
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"schema_version {version} is not supported (this checkout is v{SCHEMA_VERSION})"
            )
        return version

    @field_validator("players", mode="after")
    @classmethod
    def _exactly_one_defuser_first(cls, players: list[SubmissionPlayer]) -> list[SubmissionPlayer]:
        """A submission has exactly one defuser, and it is moved to the front for consistency."""
        defuser_indices = [idx for idx, player in enumerate(players) if player.role == "defuser"]
        if len(defuser_indices) != 1:
            raise ValueError(f"Expected exactly one defuser, got {len(defuser_indices)}")
        players.insert(0, players.pop(defuser_indices[0]))
        return players


class InteractiveSubmission(Submission[SuiteIdentity]):
    """`submission.yaml` for an interactive suite."""


class StaticsSubmission(Submission[StaticsIdentity]):
    """`submission.yaml` for a statics evaluation task."""


def parse_submission_manifest(raw: dict[str, Any]) -> InteractiveSubmission | StaticsSubmission:
    """Validate a raw manifest, discriminated on what its `measured` block describes."""
    measured = raw.get("measured")
    keys = set(measured) if isinstance(measured, dict) else set()
    if ("suite_name" in keys) == ("task_name" in keys):
        raise ValueError(
            "`measured` must describe exactly one of a suite (suite_name/…) "
            "or a statics task (task_name/…)"
        )
    model_class = InteractiveSubmission if "suite_name" in keys else StaticsSubmission
    return model_class.model_validate(raw)
