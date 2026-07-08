from __future__ import annotations

from typing import TYPE_CHECKING

from gptnt.common.hydra import load_config
from gptnt.experiments.generation.experiments import ExperimentGenerator
from gptnt.experiments.generation.pairing import PairingGenerator
from gptnt.experiments.suite.lock import SuiteLock

if TYPE_CHECKING:
    from omegaconf import DictConfig

    from gptnt.experiments.generation.pairing import PairingType
    from gptnt.experiments.spec import ExperimentSpec

CONFIG_NAME = "suite_generator"


def compose_suite(suite_name: str) -> Suite:
    """Compose and instantiate one frozen suite by name."""
    return hydra.utils.instantiate(
        load_config(config_name=CONFIG_NAME, overrides=[f"suites={suite_name}"]).suite
    )


def _best_model_for(pairing_type: PairingType, players: DictConfig) -> str | None:
    """The anchored model a `with_best_*` pairing needs, or `None` for the other pairings."""
    if pairing_type == "with_best_defuser":
        return players.best_defuser
    if pairing_type == "with_best_expert":
        return players.best_expert
    return None


def generate_specs(overrides: list[str] | None = None) -> list[ExperimentSpec]:
    """Generate the `ExperimentSpec` objects for one suite, with a roster from the config.

    The suite and its missions come from `suites.lock` (the frozen snapshot), selected by the
    `suites=<name>` override at its latest frozen revision. The roster (`players.all`) and sampling
    depth (`attempts_per_mission`) still come from the suite-generator config, which a run
    overrides. Raises `SuiteNotFrozenError` if the selected suite is not frozen.
    """
    cfg = load_config(config_name=CONFIG_NAME, overrides=overrides)
    suite, missions = SuiteLock.from_lock_path().load_suite(cfg.suite.name)

    pairings = list(
        PairingGenerator(
            pairing_type=suite.matchup.pairing_type,
            all_players=list(cfg.players.all),
            best_model=_best_model_for(suite.matchup.pairing_type, cfg.players),
        ).generate()
    )
    generator = ExperimentGenerator(
        mission_set=suite.mission_set,
        suite_name=suite.name,
        suite_revision=suite.revision,
        defuser_protocol=suite.defuser_protocol,
        expert_protocol=suite.expert_protocol,
        attempts_per_mission=cfg.attempts_per_mission,
    )
    return list(generator.generate(missions=iter(missions), pairings=iter(pairings)))
