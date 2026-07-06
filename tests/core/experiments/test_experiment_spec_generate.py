from collections.abc import Iterator
from pathlib import Path
from typing import get_args

import pytest
from omegaconf import OmegaConf
from pytest_cases import fixture, param_fixture, parametrize_with_cases

from gptnt.experiments.generation.experiments import ExperimentGenerator
from gptnt.experiments.generation.missions import (
    MissionGenerator,
    MissionGeneratorConfig,
    load_missions,
)
from gptnt.experiments.generation.pairing import Pairing, PairingGenerator, PairingType
from gptnt.experiments.generation.pipeline import _best_model_for
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.modules import KtaneComponent
from gptnt.players.specification import PlayerProtocol

from tests._cases.mission_generator_config import MissionGeneratorConfigCases

pairing_type = param_fixture("pairing_type", list(get_args(PairingType.__value__)))


def test_load_missions_raises_on_an_empty_set(tmp_path: Path) -> None:
    """Loading a set directory with no mission files fails loudly, not silently on nothing."""
    with pytest.raises(FileNotFoundError, match="No mission specs"):
        _ = load_missions(tmp_path)


def test_best_model_for_resolves_the_anchor_named_by_the_pairing() -> None:
    """A `with_best_*` pairing pulls its anchor from the roster; the others need none."""
    players = OmegaConf.create({"best_defuser": "anchor-d", "best_expert": "anchor-e"})
    assert _best_model_for("with_best_defuser", players) == "anchor-d"
    assert _best_model_for("with_best_expert", players) == "anchor-e"
    assert _best_model_for("with_self", players) is None


@parametrize_with_cases("config", cases=MissionGeneratorConfigCases)
def test_mission_generation_works(config: MissionGeneratorConfig) -> None:
    generator = MissionGenerator(config=config, num_seeds_per_mission=3, seed=42)
    missions = list(generator.generate())

    assert len(missions) == config.expected_num_missions * 3

    for mission in missions:
        assert mission.time_limit == config.time_limit
        assert mission.force_modules_to_front != config.allow_back_placement
        assert config.n_modules_min <= len(mission.components) <= config.n_modules_max
        assert (
            config.min_optional_widgets <= mission.optional_widgets <= config.max_optional_widgets
        )
        assert all(module in config.available_modules for module in mission.components), (
            "All components should be in available modules"
        )
        assert mission.seed in generator.seeds, "Seed should be one of the generated seeds"

        if config.allow_repeat_module is False:
            assert len(mission.components) == len(set(mission.components)), (
                "Components should not repeat when allow_repeat_module is False"
            )


def test_fails_when_module_repeats_required_but_disallowed() -> None:
    config = MissionGeneratorConfig(
        time_limit=60,
        allow_back_placement=True,
        n_modules_min=3,
        n_modules_max=5,
        sample_from_modules=True,
        allow_repeat_module=False,
        min_optional_widgets=1,
        max_optional_widgets=5,
        excluded_modules=set(KtaneComponent) - {KtaneComponent.big_button, KtaneComponent.keypad},
    )

    generator = MissionGenerator(config=config, num_seeds_per_mission=3, seed=42)
    with pytest.raises(
        ValueError, match="Cannot take a larger sample than population when replace is False"
    ):
        _ = list(generator.generate())


@parametrize_with_cases("config", cases=MissionGeneratorConfigCases)
def test_seed_reproducibility(config: MissionGeneratorConfig) -> None:
    generator1 = MissionGenerator(config=config, num_seeds_per_mission=3, seed=42)
    generator2 = MissionGenerator(config=config, num_seeds_per_mission=3, seed=42)
    missions1 = list(generator1.generate())
    missions2 = list(generator2.generate())

    assert missions1 == missions2


@fixture
@parametrize_with_cases("config", cases=MissionGeneratorConfigCases)
def missions(config: MissionGeneratorConfig) -> Iterator[KtaneMissionSpec]:
    generator = MissionGenerator(config=config, num_seeds_per_mission=3, seed=42)
    return generator.generate()


@fixture
def pairings(pairing_type: PairingType) -> Iterator[Pairing]:
    generator = PairingGenerator(
        pairing_type=pairing_type, all_players=["test-defuser", "test-expert"], best_model="gemini"
    )
    return generator.generate()


def test_experiment_generation_does_not_crash(
    pairing_type: PairingType, missions: Iterator[KtaneMissionSpec], pairings: Iterator[Pairing]
) -> None:
    expert_spec = PlayerProtocol(
        role="expert", communication_style="async", is_playing_alone=False, include_manual=True
    )
    generator = ExperimentGenerator(
        mission_set="single_module",
        suite_name="single-test",
        suite_revision=1,
        defuser_protocol=PlayerProtocol(
            role="defuser",
            communication_style="async",
            is_playing_alone=False,
            include_manual=False,
        ),
        expert_protocol=None if pairing_type == "no_expert" else expert_spec,
    )
    experiments = list(generator.generate(missions=missions, pairings=pairings))

    assert experiments
