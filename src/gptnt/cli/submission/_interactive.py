"""Gathering interactive experiments for a submission: the suite and its DuckDB rows."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

import hydra

from gptnt.cli.submission._schema import SubmissionExperiment
from gptnt.common.hydra import load_config
from gptnt.experiments.db.read import load_experiment_summaries, load_final_states_and_usage
from gptnt.experiments.generation.pipeline import CONFIG_NAME

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from gptnt.experiments.suite import Suite


def load_suite(suite_name: str) -> Suite:
    """Compose and instantiate one suite exactly as generation and `test_frozen_suites` do."""
    return hydra.utils.instantiate(
        load_config(config_name=CONFIG_NAME, overrides=[f"suites={suite_name}"]).suite
    )


def gather_experiments_for_suite(
    db_path: Path, suite: Suite, model_names: Iterable[str] | None = None
) -> list[SubmissionExperiment]:
    """Collate all the experiments for a given suite, filtered by model names if provided."""
    summaries = load_experiment_summaries(
        db_path, suite_name=suite.name, suite_revision=suite.revision, model_names=model_names
    )
    if not summaries:
        return []

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
    return all_experiments


def group_experiments_by_model(
    experiments: list[SubmissionExperiment],
) -> list[tuple[str, list[SubmissionExperiment]]]:
    """Group experiments into one `(model_name, experiments)` bundle group per model, name-sorted.

    Grouped by defuser capability fingerprint (not name), so the same model run with different
    capabilities lands in different bundles.
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
