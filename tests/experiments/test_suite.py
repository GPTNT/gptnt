from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError

from gptnt.common.image_ops import ImageDimensions
from gptnt.experiments.suite.core import Suite, SuiteMatchup
from gptnt.ktane.manuals.profile import KtaneContentDocument, ManualProfile
from gptnt.players.specification import PlayerProtocol

from tests._factories.experiments import (
    make_experiment_instance,
    make_experiment_spec,
    make_manual_build_definition,
)

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
        "manual_build": make_manual_build_definition().model_copy(update={"profile": _MANUAL}),
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


@pytest.mark.parametrize(
    ("changed_input", "identity_changes"),
    [
        ("profile", True),
        ("source_pin", True),
        ("language", True),
        ("rule_seed", True),
        ("image_dimensions", False),
    ],
)
def test_manual_inputs_project_into_suite_and_spec_identity(
    changed_input: Literal["profile", "source_pin", "language", "rule_seed", "image_dimensions"],
    identity_changes: bool,
) -> None:
    """Only frozen manual inputs change manual, suite, and generated-spec identity."""
    suite = _suite()
    missions = suite.loaded_missions
    spec = make_experiment_spec().model_copy(
        update={"manual_build": suite.manual_build, "suite_digest": suite.digest_for(missions)}
    )
    baseline = make_experiment_instance(spec)

    manual_build = suite.manual_build
    if changed_input == "profile":
        changed_profile = manual_build.profile.model_copy(
            update={
                "documents": (
                    KtaneContentDocument(source="ktanecontent", id="BigButton", language="en"),
                )
            }
        )
        manual_build = manual_build.model_copy(update={"profile": changed_profile})
    elif changed_input == "source_pin":
        changed_source = manual_build.sources.ktane_content.model_copy(update={"commit": "1" * 40})
        manual_build = manual_build.model_copy(
            update={
                "sources": manual_build.sources.model_copy(
                    update={"ktane_content": changed_source}
                )
            }
        )
    elif changed_input == "language":
        manual_build = manual_build.model_copy(update={"language": "fr"})
    elif changed_input == "rule_seed":
        # Pydantic rejects this unsupported value at construction. Bypass validation here only to
        # prove that a future supported seed already participates in the identity projection.
        manual_build = manual_build.model_copy(update={"rule_seed": 2})

    changed_suite = suite.model_copy(update={"manual_build": manual_build})
    changed_spec = spec.model_copy(
        update={"manual_build": manual_build, "suite_digest": changed_suite.digest_for(missions)}
    )
    changed_instance = baseline
    if changed_input == "image_dimensions":
        capabilities = changed_instance.defuser_capabilities.model_copy(
            update={"image_dimensions": ImageDimensions(width=320, height=240)}
        )
        changed_instance = changed_instance.model_copy(
            update={"defuser_capabilities": capabilities}
        )
        assert changed_instance.defuser_capabilities != baseline.defuser_capabilities

    baseline_identity = (
        suite.manual_build.fingerprint,
        suite.digest_for(missions),
        spec.fingerprint,
    )
    changed_identity = (
        manual_build.fingerprint,
        changed_suite.digest_for(missions),
        changed_spec.fingerprint,
    )
    assert (changed_identity != baseline_identity) is identity_changes


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
