from pathlib import Path

import pytest
from omegaconf import OmegaConf
from pytest_cases import parametrize_with_cases

from gptnt.experiments.generation.missions import (
    MissionGenerator,
    MissionGeneratorConfig,
    load_missions,
)
from gptnt.experiments.suite.generate import _best_model_for
from gptnt.ktane.state.modules import KNOWN_KTANE_MODULE_IDS

from tests._cases.mission_generator_config import MissionGeneratorConfigCases


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
        excluded_modules=KNOWN_KTANE_MODULE_IDS - {"BigButton", "Keypad"},
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
