import types

from gptnt.ktane.state.modules import KtaneComponent

SECONDS_PER_ACTION = 3
"""Seconds per sequential action taken."""

NUM_EXTRA_DIALOGUE_TURNS = 10
"""Number of extra dialogue turns to add to the time limit."""

NUM_ROTATION_TURNS = 8
"""Number of extra turns allowed to rotate the bomb."""

NUM_ZOOMING_TURNS_PER_MODULE = 2
"""Number of extra turns allowed for zooming in and out per module."""

MAX_NUM_STRIKES_PER_GAME = 3
"""Maximum number of strikes allowed per game."""


# Mapping of whether a module needs side info
NEEDS_SIDE_INFO = types.MappingProxyType(
    {
        KtaneComponent.wires: True,  # Needs serial number
        KtaneComponent.big_button: True,  # Needs batteries/labels
        KtaneComponent.keypad: False,
        KtaneComponent.simon: True,  # Needs serial number
        KtaneComponent.whos_on_first: False,
        KtaneComponent.memory: False,
        KtaneComponent.morse_code: False,
        KtaneComponent.venn: True,  # Needs LED indicators
        KtaneComponent.wire_sequence: False,
        KtaneComponent.maze: False,
        KtaneComponent.password: False,
    }
)
"""Whether a module needs information from the sides of the bomb."""


# Mapping of module stages
NUM_STAGES_PER_MODULE = types.MappingProxyType(
    {
        KtaneComponent.wires: 1,
        KtaneComponent.big_button: 2,  # original + after pressing
        KtaneComponent.keypad: 1,
        KtaneComponent.simon: 5,  # sequence of 5 colors flashing
        KtaneComponent.whos_on_first: 3,
        KtaneComponent.memory: 5,
        KtaneComponent.morse_code: 1,
        KtaneComponent.venn: 1,
        KtaneComponent.wire_sequence: 4,  # 4 panels
        KtaneComponent.maze: 1,
        KtaneComponent.password: 1,
    }
)

# Whether or not a module requires multiple images
NEEDS_MULTIPLE_IMAGES = types.MappingProxyType(
    {
        KtaneComponent.wires: False,
        KtaneComponent.big_button: False,
        KtaneComponent.keypad: False,
        # because of the blinking lights
        KtaneComponent.simon: True,
        KtaneComponent.whos_on_first: False,
        KtaneComponent.memory: False,
        # because of the blinking lights
        KtaneComponent.morse_code: True,
        KtaneComponent.venn: False,
        KtaneComponent.wire_sequence: False,
        KtaneComponent.maze: False,
        KtaneComponent.password: False,
    }
)

NUM_ACTION_TURNS_PER_MODULE = types.MappingProxyType(
    {
        KtaneComponent.wires: 1,  # noqa: WPS345
        # 1 for pressing the button, 9 for waiting for the timer, 1 for releasing the button
        KtaneComponent.big_button: 12,
        KtaneComponent.keypad: 4,
        # Max seq length is 5, and you have to press all the old ones too
        KtaneComponent.simon: 15,
        # Max 3 stages
        KtaneComponent.whos_on_first: 3,
        # Memory is strike specific: max 5 stages, strike resets each time,
        KtaneComponent.memory: 5,
        # 6 do nothing to gather information + up to 15 clicks set frequency + press transmit
        KtaneComponent.morse_code: 22,
        # Max 6 wires
        KtaneComponent.venn: 6,
        # 3 wires, 1 click to move to next panel, max 4 panels
        KtaneComponent.wire_sequence: (3 + 1) * 4,
        # 6x6 maze, worst case is 35 steps
        KtaneComponent.maze: 35,
        # 5 letters, 6 options for each letter
        # Need to cycle through letters twice (to communicate and set) + 1 for submitting
        KtaneComponent.password: 5 * 5 * 2 + 1,
    }
)
"""Number of turns needed per module to add to the time limit."""


def get_time_limit_for_mission(components: list[KtaneComponent]) -> int:
    """Get the time limit for a mission based on the components."""
    turns = 0
    # Add module-specific interaction actions
    turns += sum([NUM_ACTION_TURNS_PER_MODULE[component] for component in components])
    # Add one message turn per stage
    turns += sum([NUM_STAGES_PER_MODULE[component] for component in components])
    # Add rotation turns
    needs_side_info = any(NEEDS_SIDE_INFO[component] for component in components)
    number_of_rotation_turns = 2 * NUM_ROTATION_TURNS if needs_side_info else NUM_ROTATION_TURNS
    turns += number_of_rotation_turns
    # Add turns for zooming in and out
    zooms = NUM_ZOOMING_TURNS_PER_MODULE * len(components)
    # Add extra zooming turns proportional to the number of rotation turns
    zooms += 2 * number_of_rotation_turns // NUM_ROTATION_TURNS
    turns += zooms
    # Add turns for strikes
    turns += MAX_NUM_STRIKES_PER_GAME
    # Add extra dialogue turns
    turns += NUM_EXTRA_DIALOGUE_TURNS

    return turns * SECONDS_PER_ACTION
