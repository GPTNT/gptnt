import json
import types

import numpy as np

from gptnt.common.paths import Paths
from gptnt.ktane.experiments.experiments import ExperimentSpec
from gptnt.ktane.experiments.time_limits import NEEDS_SIDE_INFO, NUM_STAGES_PER_MODULE
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.modules import KtaneComponent

"""
Binning for how many images a module needs.

0 = needs only 1 image
1 = needs 2-3 Images
2 = needs 4-5 Images
3 = needs 6+
"""
"""Binning for how many images a module needs.

0 = needs only 1 image 1 = needs 2-3 Images 2 = needs 4-5 Images 3 = needs 6+
"""
NUM_IMAGES_NEEDED = types.MappingProxyType(
    {
        KtaneComponent.wires: 0,  # 1
        KtaneComponent.big_button: 1,  # 2
        KtaneComponent.keypad: 0,  # 1
        KtaneComponent.simon: 2,  # 5
        KtaneComponent.whos_on_first: 1,  # 3
        KtaneComponent.memory: 2,  # 5
        KtaneComponent.morse_code: 3,  # 33
        KtaneComponent.venn: 0,  # 1
        KtaneComponent.wire_sequence: 1,  # 3
        KtaneComponent.maze: 0,  # 1
        KtaneComponent.password: 3,  # 50
    }
)
"""Whether a users progress is affected by making a mistake."""
PROGRESS_AFFECTED_BY_STRIKES = types.MappingProxyType(
    {
        KtaneComponent.wires: 0,
        KtaneComponent.big_button: 0,
        KtaneComponent.keypad: 0,
        KtaneComponent.simon: 1,
        KtaneComponent.whos_on_first: 1,
        KtaneComponent.memory: 1,
        KtaneComponent.morse_code: 0,
        KtaneComponent.venn: 0,
        KtaneComponent.wire_sequence: 0,
        KtaneComponent.maze: 0,
        KtaneComponent.password: 0,
    }
)
""""""
BINNED_NUMBER_OF_ACTIONS_NEEDED = types.MappingProxyType(
    {
        KtaneComponent.wires: 1,
        KtaneComponent.big_button: 2,
        KtaneComponent.keypad: 1,
        KtaneComponent.simon: 2,
        KtaneComponent.whos_on_first: 1,
        KtaneComponent.memory: 1,
        KtaneComponent.morse_code: 3,
        KtaneComponent.venn: 1,
        KtaneComponent.wire_sequence: 2,
        KtaneComponent.maze: 3,
        KtaneComponent.password: 3,
    }
)

BINNED_NUM_ACTIONS_PER_MODULE = types.MappingProxyType(
    {
        KtaneComponent.wires: 1,
        KtaneComponent.big_button: 2,
        KtaneComponent.keypad: 1,
        KtaneComponent.simon: 2,
        KtaneComponent.whos_on_first: 1,
        KtaneComponent.memory: 1,
        KtaneComponent.morse_code: 3,
        KtaneComponent.venn: 1,
        KtaneComponent.wire_sequence: 2,
        KtaneComponent.maze: 3,
        KtaneComponent.password: 3,
    }
)

# configure these values to change weight of different aspects that contribute to difficulty7
# side_info, num_of_actions, num_of_stages, multiple_images, strike_affects_progress
DIFFICULTY_RATING_WEIGHTS: tuple[float, float, float, float, float] = (1, 1.5, 1, 1.5, 2)
# configure this to change how single_modules are binned by difficulty
SINGLE_MODULE_DIFFICULTY_BINNING: tuple[float, float] = (5, 10)

single_difficulty_ratings_structure: dict[str, dict[str, dict[str, float]]] = {
    "single_module": {"easy": {}, "medium": {}, "hard": {}}
}

multiple_difficulty_ratings_structure: dict[str, dict[str, float]] = {"multiple_modules_n": {}}
paths = Paths()


def get_difficulty_rating(bomb: list[KtaneComponent]) -> list[int]:
    """Calculate the difficulty rating of a bomb based on its components."""
    seen_modules: list[KtaneComponent] = []
    repeated_modules: int = 1
    needs_info_on_sides = 0
    number_of_actions_per_module = 0
    module_stages = 0
    multiple_images_needed = 0
    strike_affects_progress = 0

    for module in bomb:
        needs_info_on_sides += NEEDS_SIDE_INFO[module]
        number_of_actions_per_module += BINNED_NUMBER_OF_ACTIONS_NEEDED[module]
        module_stages += NUM_STAGES_PER_MODULE[module]
        multiple_images_needed += NUM_IMAGES_NEEDED[module]
        strike_affects_progress += PROGRESS_AFFECTED_BY_STRIKES[module]
        if module in seen_modules:
            repeated_modules += 1
        seen_modules.append(module)

    return [
        needs_info_on_sides,
        number_of_actions_per_module,
        module_stages,
        multiple_images_needed,
        strike_affects_progress,
        repeated_modules,
    ]


def calculate_ratings_of_bombs() -> None:
    """Go through each single module/multiple module n bomb and get its difficulty rating."""
    unique_missions: set[tuple[KtaneMissionSpec, str]] = get_unique_missions()
    multiple_bomb_difficulties: list[tuple[str, float]] = []
    single_bomb_difficulties: list[tuple[str, float]] = []
    for mission in unique_missions:
        if mission[1] == "single_module":
            single_bomb_difficulties.append(
                (
                    str(mission[0].components[0].value),
                    get_difficulty_sum(get_difficulty_rating(mission[0].components)),
                )
            )
        if mission[1] == "multiple_modules_n":
            multiple_bomb_difficulties.append(
                (
                    str(mission[0].seed),
                    get_difficulty_sum(get_difficulty_rating(mission[0].components)),
                )
            )

    single_bomb_difficulties.sort(key=lambda single_sort_key: single_sort_key[1])
    multiple_bomb_difficulties.sort(key=lambda multiple_sort_key: multiple_sort_key[1])

    for bomb in single_bomb_difficulties:
        single_difficulty_ratings_structure["single_module"][
            bin_difficulty(bomb[1], SINGLE_MODULE_DIFFICULTY_BINNING)
        ][bomb[0]] = bomb[1]
    for bomb in multiple_bomb_difficulties:
        multiple_difficulty_ratings_structure["multiple_modules_n"][bomb[0]] = bomb[1]

    with (paths.storage / "single_difficulty_ratings.json").open("w", encoding="utf-8") as out:
        json.dump(single_difficulty_ratings_structure, out, indent=2)
    with (paths.storage / "multiple_difficulty_ratings.json").open("w", encoding="utf-8") as out:
        json.dump(multiple_difficulty_ratings_structure, out, indent=2)


def bin_difficulty(difficulty_value: float, binning_values: tuple[float, float]) -> str:
    """Used for the single module difficulty structure."""
    if difficulty_value <= binning_values[0]:
        return "easy"
    if difficulty_value <= binning_values[1]:
        return "medium"
    return "hard"


def get_unique_missions() -> set[tuple[KtaneMissionSpec, str]]:
    """Iterates through all experiments and returns unique missions."""
    all_missions = []

    for json_file in paths.experiments.glob("*.json"):
        specs = ExperimentSpec.model_validate_json(json_file.read_text())
        all_missions.append((specs.mission_spec, specs.condition))
    unique_missions = set(all_missions)

    return unique_missions


def get_difficulty_sum(difficulty_rating: list[int]) -> float:
    """Calculates the difficulty of a given bomb."""
    *ratings, repeated_modules = difficulty_rating

    if len(ratings) != len(DIFFICULTY_RATING_WEIGHTS):
        raise ValueError("difficulty_rating and weight must be the same length")

    difficulty_before_unique_modules_modifier = sum(
        rates * weights for rates, weights in zip(ratings, DIFFICULTY_RATING_WEIGHTS, strict=True)
    )
    repeated_modules_modifier = np.log(repeated_modules)
    if repeated_modules_modifier > 0:
        final_difficulty = difficulty_before_unique_modules_modifier / repeated_modules_modifier
    else:
        final_difficulty = difficulty_before_unique_modules_modifier

    return final_difficulty


calculate_ratings_of_bombs()
