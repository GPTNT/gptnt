"""The `Suite`.

A suite is one self-contained, frozen definition of what is measured: its mission set, the per-role
interaction protocol, the matchup that pairs players, the required modalities, the capability
policy, and a revision. Two results are comparable only when the suite's `id` and `revision` and a
run's `capability_fingerprint` all match. `content_hash` detects when the measured content has
changed so the `revision` can be bumped.
"""

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal, Self, override

from annotated_types import Predicate
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, computed_field, model_validator

from gptnt.experiments.generation.pairing import PairingType
from gptnt.specification import PlayerCapabilities, PlayerProtocol

type Modality = Literal["vision", "language", "audio"]


DEFAULT_CAPABILITY_POLICY: tuple[str, ...] = (
    "image_dimensions",
    "max_observations_per_request",
    "thinking_method",
    "interaction_location_method",
    "coordinate_mode",
)
"""Default `PlayerCapabilities` fields to compare; changing any one makes results incomparable."""


def _error_if_unknown_capabilities(policy: tuple[str, ...]) -> tuple[str, ...]:
    """Raise if any entry names a non-existent `PlayerCapabilities` field."""
    unknown = sorted(set(policy) - set(PlayerCapabilities.model_fields))
    if unknown:
        raise ValueError(f"capability_policy names unknown PlayerCapabilities fields: {unknown}")
    return tuple(sorted(set(policy)))


def _digest(payload: object) -> str:
    """Short, order-stable hex digest of a JSON-able payload."""
    canonical = json.dumps(payload, sort_keys=True).encode()
    return hashlib.blake2b(canonical, digest_size=16).hexdigest()


class SuiteMatchup(BaseModel):
    """How a run's roster is paired into (defuser, expert) games."""

    model_config = ConfigDict(frozen=True)

    pairing_type: PairingType


class Suite(BaseModel):
    """One frozen benchmark configuration that defines a comparable set of results."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
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

    capability_policy: Annotated[
        tuple[str, ...], AfterValidator(_error_if_unknown_capabilities)
    ] = DEFAULT_CAPABILITY_POLICY

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

    @computed_field
    @property
    def content_hash(self) -> str:
        """Stable digest of the measured content; changes when a score-determining field does.

        Identity fields (`id`, `revision`) and the hash itself are excluded, so the digest is a
        pure fingerprint of what is measured, including the `missions_path` reference. The contents
        of that set are pinned separately by the per-suite golden gate. When this digest changes,
        the content changed and `revision` should be bumped.
        """
        payload = self.model_dump(mode="json", exclude={"id", "revision", "content_hash"})
        return _digest(payload)

    def capability_fingerprint(self, capabilities: PlayerCapabilities) -> str:
        """Digest of only the capability fields this suite's policy names.

        Restricting to `capability_policy` keeps legitimate per-model differences (a model's name,
        its structured-output mode) from splitting otherwise-comparable results into buckets.
        """
        included = capabilities.model_dump(mode="json", include=set(self.capability_policy))
        return _digest(included)

    @override
    def __hash__(self) -> int:
        return hash(self.content_hash)
