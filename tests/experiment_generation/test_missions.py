import pytest
from pytest_cases import parametrize_with_cases

from gptnt.ktane.experiments.missions import MissionGenerator, MissionGeneratorConfig
from gptnt.ktane.mission_spec import KtaneComponent


class MissionGeneratorConfigCases:
    def case_single_module(self) -> MissionGeneratorConfig:
        return MissionGeneratorConfig(
            time_limit=60,
            allow_back_placement=False,
            n_modules_min=1,
            n_modules_max=1,
            sample_from_modules=False,
            allow_repeat_module=False,
            min_optional_widgets=1,
            max_optional_widgets=5,
        )

    def case_multiple_modules(self) -> MissionGeneratorConfig:
        return MissionGeneratorConfig(
            time_limit=60,
            allow_back_placement=True,
            n_modules_min=2,
            n_modules_max=5,
            sample_from_modules=True,
            allow_repeat_module=False,
            min_optional_widgets=1,
            max_optional_widgets=5,
        )

    def case_repeated_modules(self) -> MissionGeneratorConfig:
        return MissionGeneratorConfig(
            time_limit=60,
            allow_back_placement=True,
            n_modules_min=3,
            n_modules_max=5,
            sample_from_modules=True,
            allow_repeat_module=True,
            min_optional_widgets=1,
            max_optional_widgets=5,
            # Force there to be repeated modules
            excluded_modules=set(KtaneComponent)
            - {KtaneComponent.big_button, KtaneComponent.keypad},
        )


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


@pytest.mark.xfail(
    raises=ValueError, reason="This test is expected to fail due to the config settings"
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
        max_optional_widgets=5,  # Force there to be repeated modules
        excluded_modules=set(KtaneComponent) - {KtaneComponent.big_button, KtaneComponent.keypad},
    )

    generator = MissionGenerator(config=config, num_seeds_per_mission=3, seed=42)
    _ = list(generator.generate())


@parametrize_with_cases("config", cases=MissionGeneratorConfigCases)
def test_seed_reproducibility(config: MissionGeneratorConfig) -> None:
    generator1 = MissionGenerator(config=config, num_seeds_per_mission=3, seed=42)
    generator2 = MissionGenerator(config=config, num_seeds_per_mission=3, seed=42)
    missions1 = list(generator1.generate())
    missions2 = list(generator2.generate())

    assert missions1 == missions2
