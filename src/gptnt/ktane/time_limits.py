import types

from gptnt.ktane.button_actions_per_step_size import compute_button_holding_steps
from gptnt.ktane.state.modules import KtaneModuleId

SECONDS_PER_ACTION = 3
"""Seconds per sequential action taken.

This is the same as the maximum time it takes for the game to process a single action and update
its visuals. This not the same as the maximum buffer time we build since that is different.
"""

NUM_EXTRA_DIALOGUE_TURNS = 10
"""Number of extra dialogue turns to add to the time limit."""

NUM_ROTATION_TURNS = 8
"""Number of extra turns allowed to rotate the bomb."""

MIN_ROTATIONS = 1
"""Minimum number of full rotations allowed."""

MAX_ROTATIONS = 4
"""Maximum number of full rotations allowed."""

NUM_BACK_PLACEMENT_TURNS = 8
"""Number of extra turns allowed for back placement."""

NUM_ZOOMING_TURNS_PER_MODULE = 2
"""Number of extra turns allowed for zooming in and out per module."""

MAX_NUM_STRIKES_PER_GAME = 3
"""Maximum number of strikes allowed per game."""

# Mapping of whether a module needs side info
NEEDS_SIDE_INFO = types.MappingProxyType(
    {
        "Wires": 1,
        "BigButton": 2,
        "Keypad": 0,
        "Simon": 1,
        "WhosOnFirst": 0,
        "Memory": 0,
        "Morse": 0,
        "Venn": 2,
        "WireSequence": 0,
        "Maze": 0,
        "Password": 0,
    }
)
"""Whether a module needs information from the sides of the bomb."""

# Mapping of module stages
NUM_STAGES_PER_MODULE = types.MappingProxyType(
    {
        "Wires": 1,
        "BigButton": 2,  # original + after pressing
        "Keypad": 1,
        "Simon": 5,  # sequence of 5 colors flashing
        "WhosOnFirst": 3,
        "Memory": 5,
        "Morse": 1,
        "Venn": 1,
        "WireSequence": 4,  # 4 panels
        "Maze": 1,
        "Password": 1,
    }
)

NUM_ACTIONS_PER_MODULE = types.MappingProxyType(
    {
        "Wires": 1,  # noqa: WPS345
        # 1 for pressing the button, N for waiting for the timer, 1 for releasing the button
        "BigButton": 2 + compute_button_holding_steps(SECONDS_PER_ACTION),
        "Keypad": 4,
        # Max seq length is 5, and you have to press all the old ones too
        "Simon": 15,
        # Max 3 stages
        "WhosOnFirst": 3,
        # Memory is strike specific: max 5 stages, strike resets each time,
        "Memory": 5,
        # 6 do nothing to gather info per letter + up to 15 clicks set frequency + press transmit
        "Morse": 22,
        # Max 6 wires
        "Venn": 6,
        # 3 wires, 1 click to move to next panel, max 4 panels
        "WireSequence": (3 + 1) * 4,
        # 6x6 maze, worst case is 35 steps
        "Maze": 35,
        # 5 letters, 6 options for each letter
        # Need to cycle through letters twice (to communicate and set) + 1 for submitting
        "Password": 5 * 5 * 2 + 1,
    }
)
"""Number of turns needed per module to add to the time limit."""


def get_time_limit_for_mission(
    components: list[KtaneModuleId], *, allow_back_placement: bool
) -> int:
    """Get the time limit for a mission based on the components."""
    turns = 0
    # Add module-specific interaction actions
    turns += sum([NUM_ACTIONS_PER_MODULE[component] for component in components])
    # Add one message turn per stage
    turns += sum([NUM_STAGES_PER_MODULE[component] for component in components])
    # Calculate the maximum rotations allowed based on components needing side info
    max_rotations_allowed = sum(NEEDS_SIDE_INFO[component] for component in components)
    max_rotations_allowed = min(max(max_rotations_allowed, MIN_ROTATIONS), MAX_ROTATIONS)
    # Add rotation turns
    turns += max_rotations_allowed * NUM_ROTATION_TURNS
    if allow_back_placement:
        # Add extra turns when modules can be placed on the back
        turns += NUM_BACK_PLACEMENT_TURNS
    # Add turns for zooming in and out
    zooms = NUM_ZOOMING_TURNS_PER_MODULE * len(components)
    # Add extra zooming turns proportional to the number of rotations
    zooms += 2 * max_rotations_allowed
    turns += zooms
    # Add turns for strikes
    turns += MAX_NUM_STRIKES_PER_GAME
    # Add extra dialogue turns
    turns += NUM_EXTRA_DIALOGUE_TURNS

    return turns * SECONDS_PER_ACTION
