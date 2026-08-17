from gptnt.ktane.state.module_registry import ModuleFacts, module_registry
from gptnt.ktane.time_limits import SECONDS_PER_ACTION, get_time_limit_for_mission


def test_time_limit_is_a_pure_calculation_over_facts() -> None:
    """The budget only reads the passed-in facts, not the registry."""
    facts = [
        ModuleFacts(side_info_rotations=1, num_stages=1, num_interaction_actions=1),
        ModuleFacts(side_info_rotations=2, num_stages=2, num_interaction_actions=11),
    ]

    limit = get_time_limit_for_mission(facts, allow_back_placement=False)

    # A whole number of seconds, each turn worth SECONDS_PER_ACTION.
    assert limit > 0
    assert limit % SECONDS_PER_ACTION == 0


def test_back_placement_adds_time() -> None:
    """Allowing back placement only ever increases the budget."""
    facts = [ModuleFacts()]

    without = get_time_limit_for_mission(facts, allow_back_placement=False)
    with_back = get_time_limit_for_mission(facts, allow_back_placement=True)

    assert with_back > without


def test_more_interaction_actions_extends_the_budget() -> None:
    """A module that needs more actions costs more time."""
    cheap = [ModuleFacts(num_interaction_actions=1)]
    dear = [ModuleFacts(num_interaction_actions=35)]

    assert get_time_limit_for_mission(
        dear, allow_back_placement=False
    ) > get_time_limit_for_mission(cheap, allow_back_placement=False)


def test_registry_carries_the_migrated_module_facts() -> None:
    """The shipped registry supplies the per-module time-budget facts."""
    facts = module_registry().facts("Password")

    assert facts.num_interaction_actions == 51
    assert facts.num_stages == 1
    assert facts.side_info_rotations == 0


def test_absent_module_takes_the_default_facts() -> None:
    """A community module not in the registry gets the minimal budget defaults."""
    facts = module_registry().facts("SomeCommunityModule")

    assert facts.side_info_rotations == 0
    assert facts.num_stages == 1
    assert facts.num_interaction_actions == 1
