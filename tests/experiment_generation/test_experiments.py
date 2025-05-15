from collections.abc import Iterator

from pytest_cases import fixture, parametrize, parametrize_with_cases

from gptnt.experiments.experiments import ExperimentGenerator
from gptnt.experiments.missions import MissionGenerator, MissionGeneratorConfig
from gptnt.experiments.pairing import Pairing, PairingGenerator, PairingType
from gptnt.ktane.mission_spec import KtaneMissionSpec
from tests.experiment_generation.test_missions import MissionGeneratorConfigCases
from tests.experiment_generation.test_pairings import ALL_PLAYERS


@fixture
@parametrize_with_cases("config", cases=MissionGeneratorConfigCases)
def missions(config: MissionGeneratorConfig) -> Iterator[KtaneMissionSpec]:
    generator = MissionGenerator(config=config, num_seeds_per_mission=3, seed=42)
    return generator.generate()


@fixture
@parametrize(
    "pairing_type",
    ["with_best_defuser", "with_best_expert", "with_self", "no_partner", "pairwise"],
)
def pairings(pairing_type: PairingType) -> Iterator[Pairing]:
    generator = PairingGenerator(
        pairing_type=pairing_type, all_players=ALL_PLAYERS, best_model="gemini"
    )
    return generator.generate()


def test_experiment_generation_does_not_crash(
    missions: Iterator[KtaneMissionSpec], pairings: Iterator[Pairing]
) -> None:
    generator = ExperimentGenerator(condition="multiple_modules_2", communication_style="parallel")
    experiments = list(generator.generate(missions=missions, pairings=pairings))

    assert experiments
