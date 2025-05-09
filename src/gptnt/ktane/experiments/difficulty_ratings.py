import types

from gptnt.ktane.state.modules import KtaneComponent

NEEDS_INFO_ON_SIDES = types.MappingProxyType(
    {
        KtaneComponent.wires: 1,
        KtaneComponent.big_button: 2,
        KtaneComponent.keypad: 0,
        KtaneComponent.simon: 1,
        KtaneComponent.whos_on_first: 0,
        KtaneComponent.memory: 0,
        KtaneComponent.morse_code: 0,
        KtaneComponent.venn: 2,
        KtaneComponent.wire_sequence: 0,
        KtaneComponent.maze: 0,
        KtaneComponent.password: 0,
    }
)

MODULE_STAGES = types.MappingProxyType(
    {
        KtaneComponent.wires: 0,
        KtaneComponent.big_button: 1,
        KtaneComponent.keypad: 0,
        KtaneComponent.whos_on_first: 1,
        KtaneComponent.memory: 2,
        KtaneComponent.morse_code: 0,
        KtaneComponent.venn: 0,
        KtaneComponent.wire_sequence: 2,
        KtaneComponent.maze: 0,
        KtaneComponent.password: 0,
    }
)

MULTIPLE_IMAGES_NEEDED = types.MappingProxyType(
    {
        KtaneComponent.wires: 0,
        KtaneComponent.big_button: 1,
        KtaneComponent.keypad: 0,
        KtaneComponent.whos_on_first: 2,
        KtaneComponent.memory: 3,
        KtaneComponent.morse_code: 4,
        KtaneComponent.venn: 0,
        KtaneComponent.wire_sequence: 3,
        KtaneComponent.maze: 1,
        KtaneComponent.password: 4,
    }
)

NUMBER_OF_ACTIONS_PER_MODULE = types.MappingProxyType(
    {
        KtaneComponent.wires: 0,  # noqa: WPS345
        # 1 for pressing the button, 9 for waiting for the timer, 1 for releasing the button
        KtaneComponent.big_button: 2,
        KtaneComponent.keypad: 1,
        # Max seq length is 5, and you have to press all the old ones too
        KtaneComponent.simon: 3,
        # Max 3 stages
        KtaneComponent.whos_on_first: 1,
        # Memory is strike specific: max 5 stages, strike resets each time,
        KtaneComponent.memory: 1,
        # 6 do nothing to gather information + up to 15 clicks set frequency + press transmit
        KtaneComponent.morse_code: 3,
        # Max 6 wires
        KtaneComponent.venn: 2,
        # 3 wires, 1 click to move to next panel, max 4 panels
        KtaneComponent.wire_sequence: 3,
        # 6x6 maze, worst case is 35 steps
        KtaneComponent.maze: 3,
        # 5 letters, 6 options for each letter
        # Need to cycle through letters twice (to communicate and set) + 1 for submitting
        KtaneComponent.password: 3,
    }
)

PROGRESS_AFFECTED_BY_STRIKES = types.MappingProxyType(
    {
        KtaneComponent.wires: 0,
        KtaneComponent.big_button: 0,
        KtaneComponent.keypad: 0,
        KtaneComponent.whos_on_first: 1,
        KtaneComponent.memory: 1,
        KtaneComponent.morse_code: 0,
        KtaneComponent.venn: 0,
        KtaneComponent.wire_sequence: 0,
        KtaneComponent.maze: 0,
        KtaneComponent.password: 0,
    }
)


def get_difficulty_rating(bomb: list[KtaneComponent]) -> list[int]:  # noqa: D103
    seen_modules: list[KtaneComponent] = []
    repeated_modules = 0
    needs_info_on_sides = 0
    module_stages = 0
    multiple_images_needed = 0
    number_of_actions_per_module = 0
    for module in bomb:
        needs_info_on_sides = NEEDS_INFO_ON_SIDES[module]
        module_stages = MODULE_STAGES[module]
        multiple_images_needed = MULTIPLE_IMAGES_NEEDED[module]
        number_of_actions_per_module = NUMBER_OF_ACTIONS_PER_MODULE[module]
        if module in seen_modules:
            repeated_modules += 1
    return [
        needs_info_on_sides,
        module_stages,
        multiple_images_needed,
        number_of_actions_per_module,
    ]
