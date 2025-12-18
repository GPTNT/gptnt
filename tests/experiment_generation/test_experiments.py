from collections.abc import Iterator
from typing import get_args

from pytest_cases import fixture, param_fixture, parametrize_with_cases

from gptnt.experiments.experiments import ExperimentGenerator
from gptnt.experiments.missions import MissionGenerator, MissionGeneratorConfig
from gptnt.experiments.pairing import Pairing, PairingGenerator, PairingType
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.players.specification import PlayerProtocol
from tests.experiment_generation.test_missions import MissionGeneratorConfigCases

pairing_type = param_fixture("pairing_type", list(get_args(PairingType)))


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
        condition="single_module",
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
