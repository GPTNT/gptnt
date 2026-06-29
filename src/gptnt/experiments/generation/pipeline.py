from __future__ import annotations

from typing import TYPE_CHECKING

import hydra

from gptnt.common.hydra import load_config
from gptnt.common.paths import Paths
from gptnt.experiments.generation.experiments import ExperimentGenerator
from gptnt.experiments.generation.missions import load_missions
from gptnt.experiments.generation.pairing import PairingGenerator

if TYPE_CHECKING:
    from omegaconf import DictConfig

    from gptnt.experiments.generation.pairing import PairingType
    from gptnt.experiments.spec import ExperimentSpec
    from gptnt.experiments.suite import Suite

CONFIG_NAME = "suite_generator"


def _best_model_for(pairing_type: PairingType, players: DictConfig) -> str | None:
    """The anchored model a `with_best_*` pairing needs, or `None` for the other pairings."""
    if pairing_type == "with_best_defuser":
        return players.best_defuser
    if pairing_type == "with_best_expert":
        return players.best_expert
    return None


def generate_specs(overrides: list[str] | None = None) -> list[ExperimentSpec]:
    """Generate the `ExperimentSpec` objects for one suite, with a roster from the config.

    The suite supplies the mission set, role protocols, and matchup; the roster
    (`players.all`) and sampling depth (`attempts_per_mission`) come from the suite-generator
    config, which a run overrides. Missions are loaded from the materialised set; nothing generates
    them here.
    """
    cfg = load_config(config_name=CONFIG_NAME, overrides=overrides)
    suite: Suite = hydra.utils.instantiate(cfg.suite)

    missions = load_missions(Paths().root / suite.missions_path)
    pairings = list(
        PairingGenerator(
            pairing_type=suite.matchup.pairing_type,
            all_players=list(cfg.players.all),
            best_model=_best_model_for(suite.matchup.pairing_type, cfg.players),
        ).generate()
    )
    generator = ExperimentGenerator(
        mission_set=suite.mission_set,
        defuser_protocol=suite.defuser_protocol,
        expert_protocol=suite.expert_protocol,
        attempts_per_mission=cfg.attempts_per_mission,
    )
    return list(generator.generate(missions=iter(missions), pairings=iter(pairings)))
