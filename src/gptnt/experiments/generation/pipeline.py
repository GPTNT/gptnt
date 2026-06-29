from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import hydra

from gptnt.common.hydra import load_config
from gptnt.experiments.generation.missions import load_missions

if TYPE_CHECKING:
    from gptnt.experiments.spec import ExperimentSpec

CONFIG_NAME = "experiment_generator"


def generate_specs(overrides: list[str] | None = None) -> list[ExperimentSpec]:
    """Generate the list of `ExperimentSpec` objects for a set of Hydra overrides.

    Missions are loaded from the materialised set at `missions_path`. This path never generates.
    """
    cfg = load_config(config_name=CONFIG_NAME, overrides=overrides)
    instantiated = hydra.utils.instantiate(cfg)

    missions = load_missions(Path(instantiated["missions_path"]))
    # `.generate()` returns a one-shot iterator. The experiment generator consumes pairings via
    # `itertools.product`, so materialise them first.
    pairings = list(instantiated["pairing_generator"].generate())
    return list(
        instantiated["experiment_generator"].generate(
            missions=iter(missions), pairings=iter(pairings)
        )
    )
