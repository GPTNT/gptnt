"""Tests for the frozen suite identity recorded in submission bundles."""

from gptnt.experiments.suite.definition import SuiteIdentity


def test_target_pins_name_to_revision() -> None:
    """`target` is the `name@revision` pin used as the bundle directory leaf."""
    identity = SuiteIdentity(suite_name="demo", suite_revision=4, suite_digest="0" * 32)
    assert identity.target == "demo@4"
