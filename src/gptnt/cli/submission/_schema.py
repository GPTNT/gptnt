"""Typed schema for a submission bundle: the parquet rows, the manifest, and the stats.

`submission new` writes these and `submission validate` recomputes them, so the models and
`compute_interactive_stats` are shared by both — a stat cannot mean one thing on write and another
on check.
"""

from __future__ import annotations

import json
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field

from gptnt.experiments.models import ExperimentSummary, is_valid_outcome
from gptnt.ktane.state.bomb import BombState

SCHEMA_VERSION = 1

type SubmissionKind = Literal["single-agent", "multi-agent", "other"]


class SubmissionExperiment(BaseModel):
    """One experiment in a submission: identity, the final bomb state, the outcome, and usage.

    Written as one row of `experiments.parquet`. The final `BombState` is carried so `validate` can
    re-derive the outcome from it; the per-row capability fingerprints let `validate` check the
    manifest's declared capabilities against what actually ran.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    attempt_name: str
    session_id: str
    suite_name: str
    suite_revision: int
    mission_set: str
    mission_key: str
    seed: int
    pairing: str
    defuser_name: str
    expert_name: str | None
    attempt: int
    communication_style: str

    defuser_capability_fingerprint: str
    expert_capability_fingerprint: str

    is_solved: bool
    is_detonated: bool
    is_timed_out: bool
    is_strike_out: bool
    is_hard_crash: bool
    seconds_remaining: float
    strike_count: int
    num_modules_solved: int

    final_bomb_state: BombState
    usage: dict[str, int]

    @property
    def is_valid(self) -> bool:
        """Whether this experiment counts as a valid, completed run (shared `is_valid_outcome`)."""
        return is_valid_outcome(
            is_solved=self.is_solved,
            is_timed_out=self.is_timed_out,
            is_strike_out=self.is_strike_out,
            is_hard_crash=self.is_hard_crash,
        )

    @classmethod
    def from_summary(
        cls, *, summary: ExperimentSummary, final_bomb_state: BombState, usage: dict[str, int]
    ) -> Self:
        """Project an `ExperimentSummary` (plus its final bomb state and usage) into a row."""
        return cls(
            attempt_name=summary.attempt_name,
            session_id=str(summary.session_id),
            suite_name=summary.suite_name,
            suite_revision=summary.suite_revision,
            mission_set=summary.mission_set,
            mission_key=summary.mission_key,
            seed=summary.seed,
            pairing=summary.pairing,
            defuser_name=summary.defuser_name,
            expert_name=summary.expert_name,
            attempt=summary.attempt,
            communication_style=summary.communication_style,
            defuser_capability_fingerprint=summary.defuser_capability_fingerprint,
            expert_capability_fingerprint=summary.expert_capability_fingerprint,
            is_solved=summary.is_solved,
            is_detonated=summary.is_detonated,
            is_timed_out=summary.is_timed_out,
            is_strike_out=summary.is_strike_out,
            is_hard_crash=summary.is_hard_crash,
            seconds_remaining=summary.seconds_remaining,
            strike_count=summary.strike_count,
            num_modules_solved=summary.num_modules_solved,
            final_bomb_state=final_bomb_state,
            usage=usage,
        )

    def to_row(self) -> dict[str, Any]:
        """Flatten to a parquet row: `final_bomb_state`/`usage` become JSON-string columns."""
        row = self.model_dump(mode="json", exclude={"final_bomb_state", "usage"})
        row["final_bomb_state"] = self.final_bomb_state.model_dump_json(by_alias=True)
        row["usage"] = json.dumps(self.usage)
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Self:
        """Rebuild from a parquet row, parsing the `final_bomb_state`/`usage` JSON columns."""
        return cls.model_validate(
            {
                **row,
                "final_bomb_state": json.loads(row["final_bomb_state"]),
                "usage": json.loads(row["usage"]),
            }
        )


class Submitter(BaseModel):
    """Who is submitting.

    Preserved across `submission new` re-runs.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    contact: str = ""  # @github handle or email
    affiliation: str = ""


class SystemInfo(BaseModel):
    """The model and how it is served.

    `model` is derived; the rest is submitter-declared.
    """

    model_config = ConfigDict(extra="forbid")

    model: str
    """Provider-less canonical model name (may be a HuggingFace model name).

    Derived from records.
    """

    provider: str = ""
    organization: str = ""
    is_os_model: bool = False
    type: SubmissionKind = "single-agent"
    description_url: str = ""

    expert_model: str | None = None
    """Set only when defuser and expert are different models (a mixed-model pairwise suite)."""


class Provenance(BaseModel):
    """Where the results came from in code and time."""

    model_config = ConfigDict(extra="forbid")

    gptnt_version: str
    git_sha: str | None
    run_date: str  # YYYY-MM-DD, the earliest experiment timestamp in the records


class SuiteIdentity(BaseModel):
    """The frozen suite the interactive results were measured against."""

    model_config = ConfigDict(extra="forbid")

    suite_name: str
    suite_revision: int
    suite_digest: str


class DatasetIdentity(BaseModel):
    """The frozen HuggingFace dataset a statics task was measured against."""

    model_config = ConfigDict(extra="forbid")

    hf_repo_id: str
    dataset_split: str | None = None
    requested_revision: str | None = None
    resolved_revision: str | None = None


class InteractiveSubmission(BaseModel):
    """`submission.yaml` for an interactive (KTANE) suite."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    submission_id: str

    submitter: Submitter = Field(default_factory=Submitter)
    system: SystemInfo
    capabilities: dict[str, Any]
    suite: SuiteIdentity
    provenance: Provenance
    stats: dict[str, Any]


class StaticsSubmission(BaseModel):
    """`submission.yaml` for a statics (HuggingFace no-game) task."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    submission_id: str

    submitter: Submitter = Field(default_factory=Submitter)
    system: SystemInfo
    capabilities: dict[str, Any]
    dataset: DatasetIdentity
    provenance: Provenance
    metrics: dict[str, Any]


def capability_snapshot(fingerprint: str, capabilities_dump: dict[str, Any]) -> dict[str, Any]:
    """A readable, reconstructable capability block: the full dump plus its fingerprint."""
    return {**capabilities_dump, "fingerprint": fingerprint}


def _rates(experiments: list[SubmissionExperiment]) -> dict[str, Any]:
    """Counts and outcome rates for a group of experiments (rates are over the valid subset)."""
    valid = [experiment for experiment in experiments if experiment.is_valid]
    # With no valid experiments every numerator is 0, so dividing by 1 still yields a 0 rate.
    denominator = len(valid) or 1
    return {
        "num_experiments": len(experiments),
        "num_valid": len(valid),
        "num_hard_crash": sum(1 for experiment in experiments if experiment.is_hard_crash),
        "solve_rate": sum(1 for experiment in valid if experiment.is_solved) / denominator,
        "detonate_rate": sum(1 for experiment in valid if experiment.is_detonated) / denominator,
        "timeout_rate": sum(1 for experiment in valid if experiment.is_timed_out) / denominator,
        "strikeout_rate": sum(1 for experiment in valid if experiment.is_strike_out) / denominator,
    }


def _grouped_rates(experiments: list[SubmissionExperiment], key: Any) -> dict[str, dict[str, Any]]:
    """`_rates` per group, grouped by `key(experiment)`, key-sorted for stable output."""
    groups: dict[str, list[SubmissionExperiment]] = {}
    for experiment in experiments:
        groups.setdefault(key(experiment), []).append(experiment)
    return {name: _rates(groups[name]) for name in sorted(groups)}


def _sum_usage(experiments: list[SubmissionExperiment]) -> dict[str, int]:
    """Element-wise sum of the integer usage counters across experiments."""
    total: dict[str, int] = {}
    for experiment in experiments:
        for key, count in experiment.usage.items():
            total[key] = total.get(key, 0) + count
    return total


def compute_interactive_stats(experiments: list[SubmissionExperiment]) -> dict[str, Any]:
    """The `[auto]` stats snapshot: headline rates, per-mission/per-pairing balances, usage.

    A recompute target for `validate` and a human snapshot. Not the canonical ranking source — a
    leaderboard recomputes from `experiments.parquet` under the then-current rules.
    """
    return {
        "headline": _rates(experiments),
        "balances": {
            "by_mission": _grouped_rates(experiments, lambda experiment: experiment.mission_key),
            "by_pairing": _grouped_rates(experiments, lambda experiment: experiment.pairing),
        },
        "usage": _sum_usage(experiments),
    }
