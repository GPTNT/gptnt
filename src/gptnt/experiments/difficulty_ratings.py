import json
import types

import numpy as np

from gptnt.common.paths import Paths
from gptnt.experiments.experiments import ExperimentSpec
from gptnt.experiments.time_limits import NEEDS_SIDE_INFO
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.modules import KtaneComponent

paths = Paths()

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
"""Binning for how many images a module needs.

0 = needs only 1 image 1 = needs 2-3 Images 2 = needs 4-5 Images 3 = needs 6+
"""

STAGES_PER_MODULE = types.MappingProxyType(
    {
        KtaneComponent.wires: 0,  # 1
        KtaneComponent.big_button: 0,  # 2
        KtaneComponent.keypad: 0,  # 1
        KtaneComponent.simon: 2,  # 5
        KtaneComponent.whos_on_first: 1,  # 3
        KtaneComponent.memory: 2,  # 5
        KtaneComponent.morse_code: 0,  # 1
        KtaneComponent.venn: 0,  # 1
        KtaneComponent.wire_sequence: 1,  # 4
        KtaneComponent.maze: 0,  # 1
        KtaneComponent.password: 0,  # 1
    }
)
"""Binning for how many stages there are to a module.

0 = 1-2 stages 1 = 3-4 stages 2 = 5+ stages
"""

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
"""Whether a users progress is affected by making a mistake."""


BINNED_NUMBER_OF_ACTIONS_NEEDED = types.MappingProxyType(
    {
        KtaneComponent.wires: 0,  # 1
        KtaneComponent.big_button: 0,  # 2 + compute_button_holding_steps(SECONDS_PER_ACTION) = 2 + 12 = 14
        KtaneComponent.keypad: 0,  # 4
        KtaneComponent.simon: 1,  # 15
        KtaneComponent.whos_on_first: 0,  # 3
        KtaneComponent.memory: 0,  # 5
        KtaneComponent.morse_code: 1,  # 22
        KtaneComponent.venn: 0,  # 6
        KtaneComponent.wire_sequence: 1,  # (3 + 1) * 4 = 16
        KtaneComponent.maze: 2,  # 35
        KtaneComponent.password: 2,  # 5 * 5 * 2 + 1 = 51
    }
)
"""Binning for the max number of actions needed assuming worst case and no mistakes.

0 = 0-14 1 = 15-29 2 = 30+
"""

# configure these values to change weight of different aspects that contribute to difficulty7
# side_info, num_of_actions, num_of_stages, multiple_images, strike_affects_progress
DIFFICULTY_RATING_WEIGHTS: tuple[float, float, float, float, float] = (1, 1, 2, 2, 2)
# configure this to change how single_modules are binned by difficulty
SINGLE_MODULE_DIFFICULTY_BINNING: tuple[float, float] = (5, 10)

single_difficulty_ratings_structure: dict[str, dict[str, dict[str, dict[str, float]]]] = {
    "single_module": {"easy": {}, "medium": {}, "hard": {}}
}

multiple_difficulty_ratings_structure: dict[str, dict[str, dict[str, float | list[str]]]] = {
    "multiple_modules_n": {}
}


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
        module_stages += STAGES_PER_MODULE[module]
        multiple_images_needed += int(NUM_IMAGES_NEEDED[module])
        number_of_actions_per_module += BINNED_NUMBER_OF_ACTIONS_NEEDED[module]
        strike_affects_progress += PROGRESS_AFFECTED_BY_STRIKES[module]
        if module in seen_modules:
            repeated_modules += 1
        seen_modules.append(module)

    return [
        needs_info_on_sides,
        module_stages,
        multiple_images_needed,
        number_of_actions_per_module,
        strike_affects_progress,
        repeated_modules,
    ]


def calculate_ratings_of_bombs() -> None:
    """Go through each single module/multiple module n bomb and get its difficulty rating."""
    unique_missions: set[tuple[KtaneMissionSpec, str]] = get_unique_missions()
    multiple_bomb_difficulties: list[tuple[str, float, list[int], list[str]]] = []
    single_bomb_difficulties: list[tuple[str, float, list[int]]] = []
    for mission in unique_missions:
        bomb_components = mission[0].components
        if mission[1] == "single_module":
            difficulty_rating = get_difficulty_rating(bomb_components)
            single_bomb_difficulties.append(
                (
                    str(bomb_components[0].value),
                    get_difficulty_sum(difficulty_rating),
                    difficulty_rating,
                )
            )
        if mission[1] == "multiple_modules_n":
            difficulty_rating = get_difficulty_rating(bomb_components)
            components_list: list[str] = [component.value for component in bomb_components]

            multiple_bomb_difficulties.append(
                (
                    str(mission[0].seed),
                    get_difficulty_sum(difficulty_rating),
                    difficulty_rating,
                    components_list,
                )
            )

    single_bomb_difficulties.sort(key=lambda single_sort_key: single_sort_key[1])
    multiple_bomb_difficulties.sort(key=lambda multiple_sort_key: multiple_sort_key[1])

    for bomb in single_bomb_difficulties:
        bomb_difficulty_details = bomb[2]
        single_difficulty_ratings_structure["single_module"][
            bin_difficulty(bomb[1], SINGLE_MODULE_DIFFICULTY_BINNING)
        ][bomb[0]] = {
            "difficulty": bomb[1],
            "needs_info_on_sides": bomb_difficulty_details[0],
            "module_stages": bomb_difficulty_details[1],
            "multiple_images_needed": bomb_difficulty_details[2],
            "number_of_actions_per_module": bomb_difficulty_details[3],
            "strike_affects_progress": bomb_difficulty_details[4],
        }
    for bomb in multiple_bomb_difficulties:
        bomb_difficulty_details = bomb[2]
        multiple_difficulty_ratings_structure["multiple_modules_n"][bomb[0]] = {
            "difficulty": bomb[1],
            "needs_info_on_sides": bomb_difficulty_details[0],
            "module_stages": bomb_difficulty_details[1],
            "multiple_images_needed": bomb_difficulty_details[2],
            "number_of_actions_per_module": bomb_difficulty_details[3],
            "strike_affects_progress": bomb_difficulty_details[4],
            "modules": bomb[3],
        }

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


if __name__ == "__main__":
    calculate_ratings_of_bombs()
