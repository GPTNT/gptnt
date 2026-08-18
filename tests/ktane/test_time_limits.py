from gptnt.ktane.state.module_registry import ModuleFacts, module_registry
from gptnt.ktane.time_limits import get_time_limit_for_mission


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


def test_registered_complex_module_receives_more_time() -> None:
    """Registry facts make an interaction-heavy module cost more than an unknown module."""
    registry = module_registry()

    assert get_time_limit_for_mission(
        [registry.facts("Password")], allow_back_placement=False
    ) > get_time_limit_for_mission(
        [registry.facts("SomeCommunityModule")], allow_back_placement=False
    )


def test_absent_module_takes_the_default_facts() -> None:
    """A community module not in the registry gets the minimal budget defaults."""
    facts = module_registry().facts("SomeCommunityModule")

    assert facts.side_info_rotations == 0
    assert facts.num_stages == 1
    assert facts.num_interaction_actions == 1
