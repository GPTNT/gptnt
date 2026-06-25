"""Local↔W&B parity: one outcome vocabulary, one validity definition.

These pin the convergence so it can't silently re-drift: whichever source a consumer reads — the
DuckDB `experiment_summary` row or the W&B `run.summary` — the experiment outcome has identical
field names and values, and both ledgers decide validity through the same `is_valid_outcome`. Real
`BombState`s drive every case: the bomb's `check_is_solved_condition` validator means a "not
solved" state needs a real unsolved module, so we use one.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic_ai import RunUsage

from gptnt.experiments.models import (
    ExperimentOutcome,
    ExperimentStep,
    ExperimentSummary,
    is_valid_experiment,
    is_valid_outcome,
)
from gptnt.experiments.recorder.wandb import WandbExperimentPlayerRecorder
from gptnt.experiments.wandb_runs import is_run_valid
from gptnt.ktane.state.bomb import BombState
from gptnt.players.actions import DoNothingAction
from gptnt.specification import PlayerCapabilities

from tests._factories.experiments import make_experiment_descriptor

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
    descriptor = make_experiment_descriptor()
    outcome = ExperimentOutcome.from_bomb_state(bomb, is_hard_crash=is_hard_crash)
    summary = ExperimentSummary.from_descriptor_and_bomb_state(
        descriptor=descriptor, final_bomb_state=bomb, is_hard_crash=is_hard_crash
    )

    # The DuckDB summary carries every outcome field under the same name and value.
    for field in ExperimentOutcome.model_fields:
        assert getattr(summary, field) == getattr(outcome, field), field

    # One validity definition: the shared helper (on the outcome's flags) and the local bomb-state
    # path agree.
    assert (
        is_valid_outcome(
            is_solved=outcome.is_solved,
            is_timed_out=outcome.is_timed_out,
            is_strike_out=outcome.is_strike_out,
            is_hard_crash=outcome.is_hard_crash,
        )
        is expected_valid
    )
    assert (
        is_valid_experiment(is_hard_crash=is_hard_crash, final_bomb_state=bomb) is expected_valid
    )

    # The W&B run-summary path (a finished defuser run) reaches the same verdict. A W&B Run can't
    # be built offline, so we stand in its three touched attributes with REAL outcome data — the
    # assertion still exercises the real is_run_valid logic end to end.
    run = SimpleNamespace(
        state="finished", config={"role": "defuser"}, summary=outcome.model_dump()
    )
    assert is_run_valid(run) is expected_valid


def test_outcome_field_names_are_shared_and_drift_free() -> None:
    """Every canonical outcome field is a real summary column; retired names stay gone."""
    summary_cols = set(ExperimentSummary.model_fields)
    assert set(ExperimentOutcome.model_fields) <= summary_cols
    assert _RETIRED_NAMES.isdisjoint(summary_cols)


def test_wandb_recorder_logs_canonical_outcome_names() -> None:
    """The W&B recorder logs the outcome under the canonical names, not the old drifting ones."""
    descriptor = make_experiment_descriptor()
    bomb = _bomb(solved=False, detonated=True, seconds=0)

    recorder = WandbExperimentPlayerRecorder(
        capabilities=PlayerCapabilities(player_name="test-defuser", player_type="ai")
    )
    recorder.experiment_descriptor = descriptor
    recorder.protocol = descriptor.experiment_spec.defuser_protocol
    recorder.player_uuid = descriptor.defuser_uuid
    recorder.step_records = [
        ExperimentStep(
            step=1,
            timestamp=1.0,
            role="defuser",
            session_id=descriptor.session_id,
            player_uuid=descriptor.defuser_uuid,
            player_name="test-defuser",
            output=DoNothingAction(),
            raw_output="DoNothing",
            bomb_state=bomb,
            observation=None,
            usage=RunUsage(requests=1, input_tokens=1, output_tokens=1),
            num_prompt_truncations=0,
        )
    ]

    logged = recorder._compute_data_to_send()

    expected = ExperimentOutcome.from_bomb_state(bomb, is_hard_crash=False)
    assert set(ExperimentOutcome.model_fields) <= set(logged)
    assert {"time_remaining", "total_modules_solved", "total_strikes"}.isdisjoint(logged)
    assert logged["seconds_remaining"] == expected.seconds_remaining
    assert logged["is_timed_out"] is expected.is_timed_out
    assert logged["num_modules_solved"] == expected.num_modules_solved
