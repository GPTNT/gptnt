import types

from gptnt.ktane.state.modules import KtaneComponent

SECONDS_PER_ACTION = 3
"""Seconds per sequential action taken."""

NUM_EXTRA_DIALOGUE_TURNS = 20
"""Number of extra dialogue turns to add to the time limit."""

NUM_ROTATION_TURNS = 8
"""Number of extra turns allowed to rotate the bomb."""

NUM_ZOOMING_TURNS_PER_MODULE = 3
"""Number of extra turns allowed for zooming in and output per module."""

MAX_NUM_STRIKES_PER_GAME = 3
"""Maximum number of strikes allowed per game."""

NUM_ACTION_TURNS_PER_MODULE = types.MappingProxyType(
    {
        KtaneComponent.wires: 1 * MAX_NUM_STRIKES_PER_GAME,  # noqa: WPS345
        KtaneComponent.big_button: 2 * MAX_NUM_STRIKES_PER_GAME,
        KtaneComponent.keypad: 4 * MAX_NUM_STRIKES_PER_GAME,
        # Max seq length is 6, and you have to press all the old ones too, so its a triangle numb
        KtaneComponent.simon: (6 + 7) // 2,
        # Max 3 stages
        KtaneComponent.whos_on_first: MAX_NUM_STRIKES_PER_GAME * 3,
        # memory is strike specific: max 5 stages, strike resets each time,
        KtaneComponent.memory: 5 * MAX_NUM_STRIKES_PER_GAME,
        KtaneComponent.morse_code: 60,
        # Max 6 wires
        KtaneComponent.venn: 6 * MAX_NUM_STRIKES_PER_GAME,
        # 3 wires, max 4 panels
        KtaneComponent.wire_sequence: (3 + 1) * 4,
        # Longest maze, worst case, is 19 steps
        KtaneComponent.maze: 22,
        KtaneComponent.password: 6 * 5 * 2,
    }
)
"""Number of turns needed per module to add to the time limit."""


def get_time_limit_for_mission(components: list[KtaneComponent]) -> int:
    """Get the time limit for a mission based on the components."""
    turns = 0
    turns += sum([NUM_ACTION_TURNS_PER_MODULE[component] for component in components])
    turns += NUM_ZOOMING_TURNS_PER_MODULE * len(components)
    turns += NUM_EXTRA_DIALOGUE_TURNS
    turns += NUM_ROTATION_TURNS

    return turns * SECONDS_PER_ACTION
