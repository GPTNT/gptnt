from typing import override

from pydantic import BaseModel, ConfigDict, Field

from gptnt.common.hashing import stable_digest
from gptnt.ktane.manuals.profile import ManualProfile


class ManualRequirement(BaseModel):
    """One profile compiled for the rule seed used by a suite's missions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: ManualProfile
    rule_seed: int = Field(ge=1)

    @override
    def __hash__(self) -> int:
        """Return the value hash used to deduplicate manual requirements."""
        return hash((self.profile, self.rule_seed))

    @property
    def runtime_key(self) -> str:
        """Return the environment-map key for this exact prepared manual."""
        return stable_digest(self.model_dump(mode="json"))
