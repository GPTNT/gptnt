from __future__ import annotations

from typing import TYPE_CHECKING

import hydra

from gptnt.core.common.hydra import load_config

if TYPE_CHECKING:
    from gptnt.experiments.spec import ExperimentSpec

CONFIG_NAME = "experiment_generator"


def generate_specs(overrides: list[str] | None = None) -> list[ExperimentSpec]:
    """Generate the list of `ExperimentSpec` objects for a set of Hydra overrides."""
    cfg = load_config(config_name=CONFIG_NAME, overrides=overrides)
    instantiated = hydra.utils.instantiate(cfg)

    # `.generate()` returns one-shot iterators; materialise missions/pairings into lists since the
    # experiment generator consumes them via `itertools.product`.
    missions = list(instantiated["mission_generator"].generate())
    pairings = list(instantiated["pairing_generator"].generate())
    return list(
        instantiated["experiment_generator"].generate(
            missions=iter(missions), pairings=iter(pairings)
        )
    )
