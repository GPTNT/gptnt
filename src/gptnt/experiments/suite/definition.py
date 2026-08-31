from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from annotated_types import Predicate
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from gptnt.common.hashing import stable_digest
from gptnt.common.paths import Paths
from gptnt.experiments.generation.missions import load_missions
from gptnt.experiments.generation.pairing import PairingType
from gptnt.ktane.manuals.profile import ManualProfile
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.players.specification import PlayerProtocol

type Modality = Literal["vision", "language", "audio"]


class SuiteSelector(BaseModel):
    """A suite name with an optional frozen revision selected by configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="before")
    @classmethod
    def parse_string(cls, raw_selector: Any) -> Any:
        """Parse the external `name@revision` string representation."""
        if not isinstance(raw_selector, str):
            return raw_selector

        name, separator, revision = raw_selector.rpartition("@")
        parsed_selector: dict[str, object] = {"name": raw_selector}
        if not separator:
            return parsed_selector
        if not name or "@" in name:
            raise ValueError(f"invalid suite selector: {raw_selector!r}")
        try:
            parsed_selector.update(name=name, revision=int(revision))
        except ValueError as error:
            raise ValueError(f"suite revision must be an integer: {raw_selector!r}") from error
        return parsed_selector

    @property
    def target(self) -> str:
        """The suite name with its revision when explicitly selected."""
        if self.revision is None:
            return self.name
        return f"{self.name}@{self.revision}"


class SuiteMatchup(BaseModel):
    """The pairing that turns a run's roster into (defuser, expert) games."""

    model_config = ConfigDict(frozen=True)

    pairing_type: PairingType


class Suite(BaseModel):
    """One benchmark-suite configuration that defines a comparable set of results.

    It records the mission set, per-role interaction protocol, player matchup, required modalities,
    and revision that define what is measured. A `SuiteLockEntry` records a frozen revision of this
    configuration.

    `digest` fingerprints the config and the mission files together, so a change without a
    `revision` bump is caught.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    """Suite identifier copied into lock entries, specifications, results, and submission
    targets."""

    revision: int = Field(ge=1)
    """Comparability revision that must increase when the suite's measured content changes."""

    modality: Annotated[
        tuple[Modality, ...],
        AfterValidator(lambda modalities: tuple(sorted(set(modalities)))),
        Field(min_length=1),
    ]
    """Sorted, deduplicated input modalities included in the suite configuration digest."""

    missions_path: Annotated[
        Path,
        Predicate(lambda path: not path.is_absolute()),
        Field(
            description=(
                "Repository-relative directory whose materialised missions are included in the "
                "suite digest."
            )
        ),
    ]

    defuser_protocol: Annotated[
        PlayerProtocol, Predicate(lambda protocol: protocol.role == "defuser")
    ]
    """Defuser access and action rules copied into every generated specification."""

    expert_protocol: Annotated[
        PlayerProtocol | None,
        Predicate(lambda protocol: protocol.role == "expert" or protocol is None),
    ] = None
    """Expert access and action rules copied into every generated non-solo specification."""

    matchup: SuiteMatchup

    manual_profile: ManualProfile
    """The manual required for the mission in this Suite."""

    manual_rule_seed: int = Field(default=1, ge=1)
    """Rule seed shared by the suite's bombs and its compiled manual."""

    @model_validator(mode="after")
    def validate_roles(self) -> Self:
        """Role tags must match their slots, and a solo defuser cannot have an expert."""
        if self.defuser_protocol.is_solo_player and self.expert_protocol is not None:
            raise ValueError("A solo defuser cannot have an expert.")
        return self

    @property
    def mission_set(self) -> str:
        """The mission-set name (the `missions_path` basename), grouping attempts and records."""
        return self.missions_path.name

    @property
    def loaded_missions(self) -> list[KtaneMissionSpec]:
        """Every materialised mission the suite covers, read from disk."""
        return [
            mission.model_copy(update={"rule_seed": self.manual_rule_seed})
            for mission in load_missions(Paths().root / self.missions_path)
        ]

    @property
    def mission_keys(self) -> tuple[str, ...]:
        """Sorted `mission_key` of every mission in the set, read from disk."""
        return tuple(sorted(mission.mission_key for mission in self.loaded_missions))

    def digest_payload(self, missions: Sequence[KtaneMissionSpec]) -> dict[str, object]:
        """Return the complete version-3 benchmark content represented by this suite.

        Suite labels, configuration paths, and freeze provenance intentionally do not appear here.
        The lock version fixes this exact payload recipe.
        """
        mission_payloads = [
            mission.model_dump(mode="json")
            for mission in sorted(missions, key=lambda mission: mission.digest)
        ]
        return {
            "missions": mission_payloads,
            "manual_profile": self.manual_profile.model_dump(mode="json"),
            "manual_rule_seed": self.manual_rule_seed,
            "defuser_protocol": self.defuser_protocol.model_dump(mode="json"),
            "expert_protocol": (
                self.expert_protocol.model_dump(mode="json") if self.expert_protocol else None
            ),
            "matchup": self.matchup.model_dump(mode="json"),
            "modality": self.modality,
        }

    def digest_for(self, missions: Sequence[KtaneMissionSpec]) -> str:
        """Return the suite digest for an explicit mission snapshot."""
        return stable_digest(self.digest_payload(missions))

    @property
    def digest(self) -> str:
        """A stable digest of the suite config and the current mission files.

        The full fingerprint of what the suite measures. Frozen lock entries store it alongside the
        suite revision.
        """
        return self.digest_for(self.loaded_missions)


class SuiteIdentity(BaseModel):
    """The frozen suite the interactive results were measured against."""

    model_config = ConfigDict(extra="forbid")

    suite_name: str
    suite_revision: int
    suite_digest: str

    @property
    def target(self) -> str:
        """What was measured, with its pin, the bundle dir's leaf name."""
        return f"{self.suite_name}@{self.suite_revision}"
