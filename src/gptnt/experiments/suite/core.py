from pathlib import Path
from typing import Annotated, Literal, Self

from annotated_types import Predicate
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, computed_field, model_validator

from gptnt.common.hashing import stable_digest
from gptnt.common.paths import Paths
from gptnt.experiments.generation.missions import load_missions
from gptnt.experiments.generation.pairing import PairingType
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.players.specification import PlayerProtocol

type Modality = Literal["vision", "language", "audio"]


class SuiteMatchup(BaseModel):
    """How a run's roster is paired into (defuser, expert) games."""

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
    revision: int = Field(ge=1)

    modality: Annotated[
        tuple[Modality, ...],
        AfterValidator(lambda modalities: tuple(sorted(set(modalities)))),
        Field(min_length=1),
    ]
    missions_path: Annotated[
        Path,
        Predicate(lambda path: not path.is_absolute()),
        Field(description="Relative to the repo root, not absolute."),
    ]

    defuser_protocol: Annotated[
        PlayerProtocol, Predicate(lambda protocol: protocol.role == "defuser")
    ]
    expert_protocol: Annotated[
        PlayerProtocol | None,
        Predicate(lambda protocol: protocol.role == "expert" or protocol is None),
    ]

    matchup: SuiteMatchup

    @model_validator(mode="after")
    def validate_roles(self) -> Self:
        """Role tags must match their slots, and a solo defuser admits no expert."""
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

    @property
    def missions_digest(self) -> str:
        """A stable digest of the resolved mission file contents.

        Reads the files from disk, so it changes when a mission in the set is edited even if the
        suite config is untouched.
        """
        # sort the payloads using the digest so that the ordering is stable too.
        payloads = sorted(
            [mission.model_dump_json() for mission in self.loaded_missions], key=stable_digest
        )
        return stable_digest(payloads)

    @property
    def suite_digest(self) -> str:
        """A stable digest of the whole suite: its `config_digest` and `missions_digest` combined.

        The full fingerprint of what the suite measures. `test_frozen_suites.py` pins it per
        revision, so changing the config or any mission file requires bumping `revision`.
        """
        return stable_digest([self.config_digest, self.missions_digest])
