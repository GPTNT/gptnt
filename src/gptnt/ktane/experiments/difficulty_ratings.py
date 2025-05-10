import types

from gptnt.ktane.experiments.time_limits import (
    NEEDS_SIDE_INFO,
    NUM_ACTIONS_PER_MODULE,
    NUM_STAGES_PER_MODULE,
)
from gptnt.ktane.state.modules import KtaneComponent

NUM_IMAGES_NEEDED = types.MappingProxyType(
    {
        KtaneComponent.wires: 0,
        KtaneComponent.big_button: 1,
        KtaneComponent.keypad: 0,
        KtaneComponent.simon: 5,
        KtaneComponent.whos_on_first: 2,
        KtaneComponent.memory: 3,
        KtaneComponent.morse_code: 4,
        KtaneComponent.venn: 0,
        KtaneComponent.wire_sequence: 3,
        KtaneComponent.maze: 1,
        KtaneComponent.password: 4,
    }
)

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


def get_difficulty_rating(bomb: list[KtaneComponent]) -> list[int]:
    """Calculate the difficulty rating of a bomb based on its components."""
    seen_modules: list[KtaneComponent] = []
    repeated_modules = 0
    needs_info_on_sides = 0
    module_stages = 0
    multiple_images_needed = 0
    number_of_actions_per_module = 0
    for module in bomb:
        needs_info_on_sides = NEEDS_SIDE_INFO[module]
        module_stages = NUM_STAGES_PER_MODULE[module]
        multiple_images_needed = NUM_IMAGES_NEEDED[module]
        number_of_actions_per_module = NUM_ACTIONS_PER_MODULE[module]
        if module in seen_modules:
            repeated_modules += 1
    return [
        needs_info_on_sides,
        module_stages,
        multiple_images_needed,
        number_of_actions_per_module,
    ]
