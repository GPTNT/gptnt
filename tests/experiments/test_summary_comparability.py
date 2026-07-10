"""The comparability fields `ExperimentSummary` derives from a descriptor.

`suite_name`/`suite_revision` come straight off the spec; each side's `capability_fingerprint` is a
digest of that player's full capabilities, so any setup change shifts its fingerprint.
"""

from uuid import uuid4

from whenever import Instant

from gptnt.experiments.descriptor import ExperimentDescriptor
from gptnt.experiments.models import ExperimentSummary
from gptnt.experiments.spec import ExperimentSpec
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.players.specification import PlayerCapabilities

from tests._factories.players import make_protocol

_DEFUSER_CAPS = PlayerCapabilities(
    player_name="d", player_type="ai", max_observations_per_request=8
)
_EXPERT_CAPS = PlayerCapabilities(
    player_name="e", player_type="ai", max_observations_per_request=16
)


def _solved_bomb() -> BombState:
    return BombState.model_validate(
        {
            "seed": 1,
            "maxStrikes": 3,
            "strikes": None,
            "isDetonated": False,
            "isSolved": True,
            "isLightOn": True,
            "bombSide": "front",
            "timerModule": {
                "name": "Timer",
                "onFront": True,
                "index": 0,
                "secondsRemaining": 50.0,
            },
            "widgets": [],
            "modules": [
                {
                    "wires": [{"position": 0, "isCut": True, "color": "red"}],
                    "isSolved": True,
                    "inFocus": False,
                    "onFront": True,
                    "index": 1,
                    "name": "Wires",
                }
            ],
        }
    )


def _paired_descriptor() -> ExperimentDescriptor:
    """A two-player descriptor whose spec pins a suite, with distinct per-side capabilities."""
    spec = ExperimentSpec(
        mission_spec=KtaneMissionSpec(
            seed=1, time_limit=300, num_strikes_allowed=3, components=["Wires"], optional_widgets=1
        ),
        mission_set="single_module",
        suite_name="single-pairwise-sync",
        suite_revision=2,
        defuser_protocol=make_protocol(role="defuser", is_playing_alone=False),
        defuser_name="d",
        expert_protocol=make_protocol(role="expert", is_playing_alone=False, include_manual=True),
        expert_name="e",
    )
    return ExperimentDescriptor(
        experiment_spec=spec,
        session_id=uuid4(),
        defuser_uuid=uuid4(),
        expert_uuid=uuid4(),
        game_uuid=uuid4(),
        start_time=Instant.now(),
        defuser_capabilities=_DEFUSER_CAPS,
        expert_capabilities=_EXPERT_CAPS,
    )


def _summary() -> ExperimentSummary:
    return ExperimentSummary.from_descriptor_and_bomb_state(
        descriptor=_paired_descriptor(), final_bomb_state=_solved_bomb(), is_hard_crash=False
    )


def test_suite_identity_is_carried_from_the_spec() -> None:
    """`suite_name`/`suite_revision` reach the summary unchanged."""
    summary = _summary()
    assert (summary.suite_name, summary.suite_revision) == ("single-pairwise-sync", 2)


def test_each_side_fingerprints_its_own_full_capabilities() -> None:
    """Defuser and expert fingerprints are the digests of their respective full capabilities."""
    summary = _summary()
    assert summary.defuser_capability_fingerprint == _DEFUSER_CAPS.fingerprint
    assert summary.expert_capability_fingerprint == _EXPERT_CAPS.fingerprint


def test_any_capability_change_changes_the_fingerprint() -> None:
    """Any change to a model's setup (here, its observation budget) shifts its fingerprint."""
    bumped = _DEFUSER_CAPS.model_copy(update={"max_observations_per_request": 99})
    assert _DEFUSER_CAPS.fingerprint != bumped.fingerprint
