from typing import Any

import pandas as pd

from gptnt.app.experiment_loader.scanner import ScannedExperiment
from gptnt.players.specification import PlayerRole

EXPERIMENT_META_COLUMNS = (
    "experiment_name",
    "condition",
    "seed",
    "defuser",
    "expert",
    "communication_style",
    "modules",
    "defuser_has_manual",
    "is_solved",
    "is_strike_out",
    "is_timeout",
    "num_modules_solved",
    "strike_count",
    "timer_seconds",
)


def results_to_dataframe(
    extracted_data: dict[ScannedExperiment, dict[PlayerRole, dict[str, list[Any]]]],
    fields: list[str],
) -> pd.DataFrame:
    """Convert extracted field data into a flat DataFrame.

    Each row represents one (experiment, role) combination, with extracted
    field values as additional columns alongside experiment metadata.

    Args:
        extracted_data: experiment → role → field → [values], as returned by
                        ``extract_across_file_groups``.
        fields:         Ordered list of extracted field names, used as column headers.\
    """
    rows = [
        {
            "experiment_name": experiment.experiment_name,
            "condition": experiment.condition,
            "seed": experiment.seed,
            "defuser": experiment.defuser,
            "expert": experiment.expert,
            "communication_style": experiment.communication_style,
            "modules": experiment.modules,
            "defuser_has_manual": experiment.defuser_has_manual,
            "is_solved": experiment.is_solved,
            "is_strike_out": experiment.is_strike_out,
            "is_timeout": experiment.is_timeout,
            "num_modules_solved": experiment.num_modules_solved,
            "strike_count": experiment.strike_count,
            "timer_seconds": experiment.timer_seconds,
            "role": role,
            **field_values,
        }
        for experiment, grouped in extracted_data.items()
        for role, field_values in grouped.items()
    ]
    return pd.DataFrame(rows, columns=[*EXPERIMENT_META_COLUMNS, "role", *fields])  # pyright: ignore[reportArgumentType]
