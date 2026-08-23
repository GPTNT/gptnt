from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Literal, Self

from annotated_types import Predicate
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, computed_field, model_validator

from gptnt.common.hashing import stable_digest
from gptnt.common.paths import Paths
from gptnt.experiments.generation.missions import load_missions
from gptnt.experiments.generation.pairing import PairingType
from gptnt.ktane.manuals.profile import ManualProfile
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.players.specification import PlayerProtocol

type Modality = Literal["vision", "language", "audio"]


class SuiteMatchup(BaseModel):
    """The pairing that turns a run's roster into (defuser, expert) games."""

    model_config = ConfigDict(frozen=True)

    pairing_type: PairingType


class Suite(BaseModel):
    """One frozen benchmark configuration that defines a comparable set of results.

    This is a frozen definition of what is measured: its mission set, the per-role interaction
    protocol, the matchup that pairs players, the required modalities, and a revision.

    `suite_digest` fingerprints the config and the mission files together, so a change without a
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
    ]
    """Expert access and action rules copied into every generated non-solo specification."""

    matchup: SuiteMatchup

    manual_profile: ManualProfile
    """The manual required for the mission in this Suite."""

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
        return load_missions(Paths().root / self.missions_path)

    @property
    def mission_keys(self) -> tuple[str, ...]:
        """Sorted `mission_key` of every mission in the set, read from disk."""
        return tuple(sorted(mission.mission_key for mission in self.loaded_missions))

    @computed_field
    @property
    def config_digest(self) -> str:
        """A stable digest of the suite's config itself."""
        payload = self.model_dump(mode="json", exclude={"name", "revision", "config_digest"})
        return stable_digest(payload)

    def digest_for(self, missions: Sequence[KtaneMissionSpec]) -> str:
        """Calculate this suite's digest from an explicit mission snapshot."""
        # sort the payloads using the digest so that the ordering is stable too.
        payloads = sorted([mission.model_dump_json() for mission in missions], key=stable_digest)
        missions_digest = stable_digest(payloads)
        return stable_digest([self.config_digest, missions_digest])

    @property
    def suite_digest(self) -> str:
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
