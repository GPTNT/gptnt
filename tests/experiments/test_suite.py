from pathlib import Path

import pytest
from pydantic import ValidationError

from gptnt.experiments.suite.definition import Suite, SuiteMatchup
from gptnt.ktane.manuals.profile import KtaneContentDocument, ManualProfile
from gptnt.players.specification import PlayerProtocol

_DEFUSER = PlayerProtocol(
    role="defuser", communication_style="sync", is_playing_alone=False, include_manual=False
)
_EXPERT = PlayerProtocol(
    role="expert", communication_style="sync", is_playing_alone=False, include_manual=True
)
_MANUAL = ManualProfile(
    include_frontmatter=False,
    documents=(KtaneContentDocument(source="ktanecontent", id="Wires", language="en"),),
)


def _suite(**overrides: object) -> Suite:
    """Build a baseline valid suite, overriding individual fields per test."""
    fields: dict[str, object] = {
        "name": "multi-self-sync",
        "revision": 1,
        "modality": ("vision", "language"),
        "missions_path": Path("configs/missions/multiple_module_n"),
        "defuser_protocol": _DEFUSER,
        "expert_protocol": _EXPERT,
        "matchup": SuiteMatchup(pairing_type="with_self"),
        "manual_profile": _MANUAL,
    }
    fields.update(overrides)
    return Suite.model_validate(fields)


def test_suite_digest_changes_with_a_materialised_mission_body() -> None:
    """The complete materialised mission specification is part of the benchmark contract."""
    suite = _suite()
    missions = suite.loaded_missions
    changed_missions = [
        missions[0].model_copy(update={"time_limit": missions[0].time_limit + 1}),
        *missions[1:],
    ]

    assert suite.digest_for(missions) != suite.digest_for(changed_missions)


def test_suite_digest_changes_with_manual_profile() -> None:
    """Changing the manual made available to the expert changes what the benchmark measures."""
    suite = _suite()
    changed = suite.model_copy(
        update={
            "manual_profile": suite.manual_profile.model_copy(update={"include_frontmatter": True})
        }
    )

    assert suite.digest != changed.digest


def test_suite_digest_changes_with_explicit_manual_rule_seed() -> None:
    """The manual rule seed is a direct digest input with an unchanged mission snapshot."""
    suite = _suite()
    changed = suite.model_copy(update={"manual_rule_seed": 7})

    assert suite.digest_for(suite.loaded_missions) != changed.digest_for(suite.loaded_missions)


def test_suite_digest_changes_with_defuser_protocol() -> None:
    """Defuser interaction permissions are benchmark-affecting."""
    suite = _suite()
    changed = suite.model_copy(
        update={
            "defuser_protocol": suite.defuser_protocol.model_copy(
                update={"allow_magic_actions": True}
            )
        }
    )

    assert suite.digest != changed.digest


def test_suite_digest_changes_with_expert_protocol() -> None:
    """Expert interaction permissions are benchmark-affecting."""
    suite = _suite()
    assert suite.expert_protocol is not None
    changed = suite.model_copy(
        update={
            "expert_protocol": suite.expert_protocol.model_copy(
                update={"allow_magic_actions": True}
            )
        }
    )

    assert suite.digest != changed.digest


def test_suite_digest_changes_with_matchup() -> None:
    """Player pairing changes what a suite measures."""
    suite = _suite()
    changed = suite.model_copy(update={"matchup": SuiteMatchup(pairing_type="pairwise")})

    assert suite.digest != changed.digest


def test_suite_digest_changes_with_modality() -> None:
    """Required model modalities are benchmark-affecting."""
    suite = _suite()
    changed = suite.model_copy(update={"modality": ("audio", "language")})

    assert suite.digest != changed.digest


def test_suite_digest_ignores_mission_order() -> None:
    """Mission order does not affect the digest because the bodies are sorted by digest."""
    suite = _suite()
    missions = suite.loaded_missions

    assert suite.digest_for(missions) == suite.digest_for(list(reversed(missions)))


def test_manual_rule_seed_replaces_each_materialised_mission_rule_seed() -> None:
    """The suite, rather than individual mission files, selects the manual's generated rules."""
    suite = _suite(manual_rule_seed=7)

    assert {mission.rule_seed for mission in suite.loaded_missions} == {7}


def test_mission_set_derives_from_missions_path() -> None:
    """The grouping label is the mission-set directory name, not a separate field."""
    assert _suite().mission_set == "multiple_module_n"


def test_modality_is_canonicalised() -> None:
    """Listed modality order and duplicates never reach the hash."""
    assert _suite(modality=("language", "vision", "language")).modality == ("language", "vision")


def test_absolute_missions_path_is_rejected() -> None:
    """An absolute mission path is not a portable authoring configuration."""
    with pytest.raises(ValidationError, match="missions_path"):
        _ = _suite(missions_path=Path("/abs/missions"))


def test_solo_defuser_cannot_have_expert() -> None:
    """A solo defuser paired with an expert raises an error."""
    solo = PlayerProtocol(
        role="defuser", communication_style="sync", is_playing_alone=True, include_manual=False
    )
    with pytest.raises(ValidationError, match="solo defuser cannot have an expert"):
        _ = _suite(defuser_protocol=solo, expert_protocol=_EXPERT)


def test_defuser_slot_must_hold_a_defuser() -> None:
    """The defuser slot rejects an expert-roled protocol."""
    with pytest.raises(ValidationError, match="defuser_protocol"):
        _ = _suite(defuser_protocol=_EXPERT)
