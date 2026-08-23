from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from gptnt.cli.submission._schema import SubmissionExperiment
from gptnt.experiments.db.read import load_experiment_summaries, load_final_states_and_usage
from gptnt.experiments.suite.definition import SuiteIdentity

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

    from gptnt.experiments.records import ExperimentSummary


def suite_identity_from_experiments(experiments: Sequence[ExperimentSummary]) -> SuiteIdentity:
    """Return the shared recorded suite identity, rejecting a mixed selection."""
    identities = {
        (experiment.suite_name, experiment.suite_revision, experiment.suite_digest)
        for experiment in experiments
    }
    if len(identities) != 1:
        found = ", ".join(
            f"{name}@{revision} ({digest})" for name, revision, digest in sorted(identities)
        )
        raise ValueError(f"Cannot bundle experiments with conflicting suite identities: {found}")
    suite_name, suite_revision, suite_digest = next(iter(identities))
    return SuiteIdentity(
        suite_name=suite_name, suite_revision=suite_revision, suite_digest=suite_digest
    )


def gather_experiments_for_suite(
    db_path: Path, suite_name: str, model_names: Iterable[str] | None = None
) -> tuple[SuiteIdentity | None, list[SubmissionExperiment]]:
    """Collate one suite's experiments and their shared recorded identity."""
    summaries = load_experiment_summaries(db_path, suite_name=suite_name, model_names=model_names)
    if not summaries:
        return None, []
    identity = suite_identity_from_experiments(summaries)

    final_states = load_final_states_and_usage(
        db_path, [summary.session_id for summary in summaries]
    )
    all_experiments = []
    for summary in summaries:
        # If there is an issue with the session ID, this should fail.
        final_bomb_state, usage_by_role = final_states[summary.session_id]
        all_experiments.append(
            SubmissionExperiment.from_summary(
                summary=summary, final_bomb_state=final_bomb_state, usage_by_role=usage_by_role
            )
        )
    return identity, all_experiments


def group_experiments_by_model(
    experiments: list[SubmissionExperiment],
) -> list[tuple[str, list[SubmissionExperiment]]]:
    """Group experiments into one `(model_name, experiments)` bundle group per model, name-sorted.

    Grouped by defuser capability fingerprint (not name), so the same model run with different
    capabilities goes into a different bundle.
    """
    groups: dict[str, list[SubmissionExperiment]] = defaultdict(list)
    for experiment in experiments:
        groups[experiment.defuser_capability_fingerprint].append(experiment)

    return sorted(
        (
            (group_experiments[0].defuser_capabilities.player_name, group_experiments)
            for group_experiments in groups.values()
        ),
        key=lambda group: group[0],
    )
