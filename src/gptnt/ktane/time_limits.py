from gptnt.ktane.state.module_registry import ModuleFacts

SECONDS_PER_ACTION = 3
"""Seconds per sequential action taken.

This is the same as the maximum time it takes for the game to process one action and update its
visuals. This not the same as the maximum buffer time we build since that is different. You should
not change this because changing it can have unintended consequences on the time limit calculation.
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


def get_time_limit_for_mission(
    module_facts: list[ModuleFacts], *, allow_back_placement: bool
) -> int:
    """Get the time limit for a mission from the facts of its modules.

    The caller must provide the `ModuleFacts` for each component (from the module registry) so this
    stays a pure calculation over facts.
    """
    turns = 0
    # Add module-specific interaction actions
    turns += sum(facts.num_interaction_actions for facts in module_facts)
    # Add one message turn per stage
    turns += sum(facts.num_stages for facts in module_facts)
    # Calculate the maximum rotations allowed based on components needing side info
    max_rotations_allowed = sum(facts.side_info_rotations for facts in module_facts)
    max_rotations_allowed = min(max(max_rotations_allowed, MIN_ROTATIONS), MAX_ROTATIONS)
    # Add rotation turns
    turns += max_rotations_allowed * NUM_ROTATION_TURNS
    if allow_back_placement:
        # Add extra turns when modules can be placed on the back
        turns += NUM_BACK_PLACEMENT_TURNS
    # Add turns for zooming in and out
    zooms = NUM_ZOOMING_TURNS_PER_MODULE * len(module_facts)
    # Add extra zooming turns proportional to the number of rotations
    zooms += 2 * max_rotations_allowed
    turns += zooms
    # Add turns for strikes
    turns += MAX_NUM_STRIKES_PER_GAME
    # Add extra dialogue turns
    turns += NUM_EXTRA_DIALOGUE_TURNS

    return turns * SECONDS_PER_ACTION
