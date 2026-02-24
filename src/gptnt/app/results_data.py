from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from gptnt.players.metrics.records import ExperimentRecord


def extract_summary_row(experiment: ExperimentRecord) -> dict[str, Any]:
    """Extract a flat summary dict from a single record.

    Only fields that do *not* require observations or messages are used, so this is safe to call on
    records loaded via the lightweight loader.
    """
    spec = experiment.experiment_descriptor.experiment_spec
    mission = spec.mission_spec

    modules = ", ".join(sorted({comp.value for comp in mission.components}))

    # PlayerRole is a Literal type alias ("defuser" | "expert"), not an Enum
    defuser_steps = sum(1 for step in experiment.step_records if step.role == "defuser")
    expert_steps = sum(1 for step in experiment.step_records if step.role == "expert")

    return {
        "Condition": spec.condition,
        "Comm Style": spec.communication_style,
        "Modules": modules,
        "Seed": mission.seed,
        "Defuser": spec.defuser_name,
        "Expert": spec.expert_name or "—",
        "Defuser Steps": defuser_steps,
        "Expert Steps": expert_steps,
    }


def build_results_dataframe(experiments: list[ExperimentRecord]) -> pd.DataFrame:
    """Build a :class:`pandas.DataFrame` from a list of experiment records.

    Args:
        experiments: Experiment records to summarise.

    Returns:
        DataFrame with one row per experiment record, columns from
        :func:`extract_summary_row`.
    """
    rows = [extract_summary_row(exp) for exp in experiments]
    return pd.DataFrame(rows)
