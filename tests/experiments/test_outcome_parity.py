"""Local↔W&B parity: one outcome vocabulary, one validity definition.

These pin the convergence so it can't silently re-drift: whichever source a consumer reads — the
DuckDB `experiment_summary` row or the W&B `run.summary` — the experiment outcome has identical
field names and values, and both ledgers decide validity through the same `is_valid_outcome`. Real
`BombState`s drive every case: the bomb's `check_is_solved_condition` validator means a "not
solved" state needs a real unsolved module, so we use one.
"""

from __future__ import annotations

import pytest
from pydantic_ai import RunUsage

from gptnt.experiments.recorder.wandb import WandbExperimentPlayerRecorder
from gptnt.experiments.records import (
    ExperimentOutcome,
    ExperimentStep,
    ExperimentSummary,
    is_valid_outcome,
)
from gptnt.ktane.state.bomb import BombOutcome, BombState
from gptnt.players.actions import DoNothingAction
from gptnt.players.specification import PlayerCapabilities

from tests._factories.experiments import make_experiment_instance, make_provenance

# Names retired by the convergence — must never reappear as summary columns or logged metrics.
_RETIRED_NAMES = frozenset(
    ("time_remaining", "total_modules_solved", "total_strikes", "is_timeout")
)


def _module(*, solved: bool) -> dict[str, object]:
    """A single Wires module (solved or not) for a test BombState."""
    return {
        "wires": [{"position": 0, "isCut": False, "color": "red"}],
        "isSolved": solved,
        "inFocus": False,
        "onFront": True,
        "index": 1,
        "name": "Wires",
    }


def _bomb(
    *, solved: bool, detonated: bool, seconds: float, strikes: list[str] | None = None
) -> BombState:
    """A real final BombState with a single (un)solved module so `is_solved` is honoured."""
    return BombState.model_validate(
        {
            "seed": 1,
            "maxStrikes": 3,
            "strikes": strikes,
            "isDetonated": detonated,
            "isSolved": solved,
            "isLightOn": True,
            "bombSide": "front",
            "timerModule": {
                "name": "Timer",
                "onFront": True,
                "index": 0,
                "secondsRemaining": seconds,
            },
            "widgets": [],
            "modules": [_module(solved=solved)],
        }
    )


# (label, bomb, is_hard_crash, expected_valid). `seconds=0` (int) is the zero-time case — pydantic
# coerces it to the float field, and it keeps WPS off a float-zero literal.
_CASES = (
    ("solved", _bomb(solved=True, detonated=False, seconds=100.0), False, True),
    ("timed_out", _bomb(solved=False, detonated=True, seconds=0), False, True),
    (
        "strike_out",
        _bomb(solved=False, detonated=True, seconds=50.0, strikes=["Wires", "Wires", "Wires"]),
        False,
        True,
    ),
    ("detonated", _bomb(solved=False, detonated=True, seconds=50.0), False, False),
    ("abandoned", _bomb(solved=False, detonated=False, seconds=50.0), False, False),
    ("solved_but_crashed", _bomb(solved=True, detonated=False, seconds=100.0), True, False),
)


@pytest.mark.parametrize(
    ("bomb", "is_hard_crash", "expected_valid"),
    [case[1:] for case in _CASES],
    ids=[case[0] for case in _CASES],
)
def test_outcome_and_validity_parity(
    bomb: BombState, is_hard_crash: bool, expected_valid: bool
) -> None:
    """The DB summary, the W&B run summary, and both validity checks all agree per outcome."""
    instance = make_experiment_instance()
    summary = ExperimentSummary.from_instance_and_bomb_state(
        instance=instance,
        final_bomb_state=bomb,
        is_hard_crash=is_hard_crash,
        provenance=make_provenance(),
    )

    # The DuckDB summary carries every outcome field under the same name and value.
    assert summary.outcome is bomb.outcome
    assert summary.seconds_remaining == bomb.seconds_remaining
    assert summary.strike_count == bomb.strike_count
    assert summary.num_modules_solved == bomb.num_modules_solved
    assert summary.is_hard_crash is is_hard_crash

    # One validity definition: the shared helper (on the outcome's flags) and the local bomb-state
    # path agree.
    assert is_valid_outcome(outcome=bomb.outcome, is_hard_crash=is_hard_crash) is expected_valid


def test_timeout_takes_precedence_if_terminal_signals_overlap() -> None:
    """Preserve deterministic classification for a state the old flags allowed."""
    bomb = _bomb(solved=False, detonated=True, seconds=0, strikes=["Wires", "Wires", "Wires"])

    assert bomb.outcome is BombOutcome.timeout


def test_outcome_field_names_are_shared_and_drift_free() -> None:
    """Every canonical outcome field is a real summary column; retired names stay gone."""
    summary_cols = set(ExperimentSummary.model_fields)
    assert set(ExperimentOutcome.model_fields) <= summary_cols
    assert _RETIRED_NAMES.isdisjoint(summary_cols)


def test_wandb_recorder_logs_canonical_outcome_names() -> None:
    """The W&B recorder logs the outcome under the canonical names, not the old drifting ones."""
    instance = make_experiment_instance()
    bomb = _bomb(solved=False, detonated=True, seconds=0)

    recorder = WandbExperimentPlayerRecorder(
        capabilities=PlayerCapabilities(player_name="test-defuser", player_type="ai")
    )
    recorder.provenance = make_provenance()
    recorder.experiment_instance = instance
    recorder.protocol = instance.defuser_protocol
    recorder.player_uuid = instance.defuser_uuid
    recorder.step_records = [
        ExperimentStep(
            step=1,
            timestamp=1.0,
            role="defuser",
            session_id=instance.session_id,
            player_uuid=instance.defuser_uuid,
            player_name="test-defuser",
            output=DoNothingAction(),
            raw_output="DoNothing",
            bomb_state=bomb,
            observation=None,
            usage=RunUsage(requests=1, input_tokens=1, output_tokens=1),
            num_prompt_truncations=0,
        )
    ]

    logged = recorder._compute_data_to_send(recorder.build_player_record())

    assert set(ExperimentOutcome.model_fields) <= set(logged)
    assert {"time_remaining", "total_modules_solved", "total_strikes"}.isdisjoint(logged)
    assert logged["outcome"] == BombOutcome.timeout
    assert logged["seconds_remaining"] == bomb.seconds_remaining
    assert logged["num_modules_solved"] == bomb.num_modules_solved
    assert logged["is_solved"] is False
    assert logged["is_detonated"] is True
    assert logged["is_timed_out"] is True
    assert logged["is_strike_out"] is False

    crashed = recorder._compute_data_to_send(recorder.build_player_record(is_hard_crash=True))
    assert crashed["outcome"] == BombOutcome.timeout
    assert crashed["is_hard_crash"] is True
