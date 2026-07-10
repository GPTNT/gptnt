"""Tests for the frozen suite identity carried in submission bundles."""

from __future__ import annotations

from pathlib import Path

from gptnt.experiments.suite.core import Suite, SuiteIdentity, SuiteMatchup
from gptnt.players.specification import PlayerProtocol

_DEFUSER = PlayerProtocol(
    role="defuser", communication_style="sync", is_playing_alone=False, include_manual=False
)
_EXPERT = PlayerProtocol(
    role="expert", communication_style="sync", is_playing_alone=False, include_manual=True
)


def _suite(**overrides: object) -> Suite:
    """Build a baseline valid suite, overriding individual fields per test."""
    fields: dict[str, object] = {
        "name": "multi-self-sync",
        "revision": 3,
        "modality": ("vision", "language"),
        "missions_path": Path("configs/missions/multiple_module_n"),
        "defuser_protocol": _DEFUSER,
        "expert_protocol": _EXPERT,
        "matchup": SuiteMatchup(pairing_type="with_self"),
    }
    fields.update(overrides)
    return Suite.model_validate(fields)


def test_from_suite_snapshots_name_revision_and_digest() -> None:
    """`from_suite` copies the suite's identity fields verbatim."""
    suite = _suite()
    identity = SuiteIdentity.from_suite(suite)

    assert (identity.suite_name, identity.suite_revision, identity.suite_digest) == (
        suite.name,
        suite.revision,
        suite.suite_digest,
    )


def test_target_pins_name_to_revision() -> None:
    """`target` is the `name@revision` pin used as the bundle directory leaf."""
    assert SuiteIdentity.from_suite(_suite(name="demo", revision=4)).target == "demo@4"
