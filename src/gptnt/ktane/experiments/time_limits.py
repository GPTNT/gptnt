import types

from gptnt.ktane.state.modules import KtaneComponent

SECONDS_PER_ACTION = 3
"""Seconds per sequential action taken."""

NUM_EXTRA_DIALOGUE_TURNS = 30
"""Number of extra dialogue turns to add to the time limit."""

NUM_ZOOMING_TURNS_PER_MODULE = 3
"""Number of extra turns allowed for zooming in and output per module."""

NUM_TURNS_PER_MODULE = types.MappingProxyType(
    {
        KtaneComponent.wires: 60,
        KtaneComponent.big_button: 60,
        KtaneComponent.keypad: 60,
        KtaneComponent.simon: 60,
        KtaneComponent.whos_on_first: 60,
        KtaneComponent.memory: 60,
        KtaneComponent.morse_code: 60,
        KtaneComponent.venn: 60,
        KtaneComponent.wire_sequence: 60,
        KtaneComponent.maze: 60,
        KtaneComponent.password: 60,
    }
)
"""Number of turns needed per module to add to the time limit."""


def get_time_limit_for_mission(components: list[KtaneComponent]) -> int:
    """Get the time limit for a mission based on the components."""
    turns = 0
    turns += sum([NUM_TURNS_PER_MODULE[component] for component in components])
    turns += NUM_ZOOMING_TURNS_PER_MODULE * len(components)
    turns += NUM_EXTRA_DIALOGUE_TURNS

    return turns * SECONDS_PER_ACTION
