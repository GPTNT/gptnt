"""Manual requirements keep a manual profile and its rule seed together."""

from gptnt.ktane.manuals.requirement import ManualRequirement

from tests._factories.experiments import make_manual_profile


def test_rule_seed_distinguishes_requirements_with_the_same_profile() -> None:
    """Different generated rules require separately addressable prepared manuals."""
    profile = make_manual_profile()
    first = ManualRequirement(profile=profile, rule_seed=1)
    second = ManualRequirement(profile=profile, rule_seed=2)

    assert first.runtime_key != second.runtime_key
