from pathlib import Path

import pytest
from pydantic import ValidationError

from gptnt.experiments.suite import Suite, SuiteMatchup
from gptnt.specification import PlayerProtocol

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
        "revision": 1,
        "modality": ("vision", "language"),
        "missions_path": Path("configs/missions/multiple_module_n"),
        "defuser_protocol": _DEFUSER,
        "expert_protocol": _EXPERT,
        "matchup": SuiteMatchup(pairing_type="with_self"),
    }
    fields.update(overrides)
    return Suite.model_validate(fields)


def test_config_digest_ignores_identity() -> None:
    """A different name or revision over identical config yields the same config_digest."""
    assert _suite().config_digest == _suite(name="renamed", revision=9).config_digest


def test_config_digest_tracks_missions_path() -> None:
    """Pointing at a different mission set changes the config_digest."""
    assert (
        _suite().config_digest
        != _suite(missions_path=Path("configs/missions/single_module")).config_digest
    )


def test_config_digest_tracks_matchup() -> None:
    """Changing who plays whom changes the config_digest."""
    assert (
        _suite().config_digest
        != _suite(matchup=SuiteMatchup(pairing_type="pairwise")).config_digest
    )


def test_mission_set_derives_from_missions_path() -> None:
    """The grouping label is the mission-set directory name, not a separate field."""
    assert _suite().mission_set == "multiple_module_n"


def test_modality_is_canonicalised() -> None:
    """Listed modality order and duplicates never reach the hash."""
    assert _suite(modality=("language", "vision", "language")).modality == ("language", "vision")


def test_absolute_missions_path_is_rejected() -> None:
    """An absolute set path would make config_digest machine-dependent, so it is rejected."""
    with pytest.raises(ValidationError, match="missions_path"):
        _ = _suite(missions_path=Path("/abs/missions"))


def test_solo_defuser_cannot_have_expert() -> None:
    """A solo defuser paired with an expert fails loudly."""
    solo = PlayerProtocol(
        role="defuser", communication_style="sync", is_playing_alone=True, include_manual=False
    )
    with pytest.raises(ValidationError, match="solo defuser cannot have an expert"):
        _ = _suite(defuser_protocol=solo, expert_protocol=_EXPERT)


def test_defuser_slot_must_hold_a_defuser() -> None:
    """The defuser slot rejects an expert-roled protocol."""
    with pytest.raises(ValidationError, match="defuser_protocol"):
        _ = _suite(defuser_protocol=_EXPERT)
