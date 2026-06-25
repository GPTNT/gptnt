from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from gptnt.experiments.ledger.base import Source
from gptnt.experiments.ledger.local import LocalLedger
from gptnt.experiments.ledger.resolve import resolve_ledger
from gptnt.experiments.recorder.parquet import (
    RecordFooter,
    build_footer,
    write_player_record_parquet,
)
from gptnt.ktane.state.bomb import BombState

from tests._factories.experiments import make_experiment_descriptor, make_experiment_spec

if TYPE_CHECKING:
    from pathlib import Path


def _completed_bomb_state() -> BombState:
    """A bomb whose modules are all solved."""
    return BombState.model_validate(
        {
            "seed": 12345,
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
                "secondsRemaining": 100.0,
            },
            "widgets": [],
            "modules": [],
        }
    )


def _write_completed(output_dir: Path, *, seed: int, is_hard_crash: bool = False) -> str:
    """Write a recorded output that reached a final (completed) bomb state.

    Returns the attempt name the ledger will key off (read from the footer's descriptor).
    """
    return _write(
        output_dir, seed=seed, final_bomb_state=_completed_bomb_state(), crash=is_hard_crash
    )


def _write_never_completed(output_dir: Path, *, seed: int) -> str:
    """Write a recorded output that never reached a bomb state (crashed before the first step)."""
    return _write(output_dir, seed=seed, final_bomb_state=None, crash=False)


def _write(output_dir: Path, *, seed: int, final_bomb_state: BombState | None, crash: bool) -> str:
    """Write a parquet record whose footer carries the attempt name and outcome the ledger reads.

    The seed makes each descriptor's `attempt_name` distinct; the filename intentionally does *not*
    encode it, so these tests prove the ledger keys off the footer, not the filename.
    """
    descriptor = make_experiment_descriptor(make_experiment_spec(seed=seed))
    footer_model = RecordFooter(
        descriptor=descriptor,
        final_bomb_state=final_bomb_state,
        is_hard_crash=crash,
        role="defuser",
    )
    footer = build_footer(footer_model, player_uuid=str(uuid4()))
    path = output_dir / f"experiment-{uuid4()}.parquet"
    write_player_record_parquet(blobbed_steps=[], footer=footer, output_path=path)
    return descriptor.name


def test_status_for_classifies_each_outcome(tmp_path: Path) -> None:
    done = _write_completed(tmp_path, seed=1)
    crashed = _write_completed(tmp_path, seed=2, is_hard_crash=True)
    incomplete = _write_never_completed(tmp_path, seed=3)

    ledger = LocalLedger(output_dir=tmp_path)
    statuses = ledger.status_for([done, crashed, incomplete, "never-run-exp"])

    assert statuses == {
        done: "done",
        crashed: "failed",  # a hard crash is never valid, even with a final bomb state
        incomplete: "failed",  # never reached a final bomb state
        "never-run-exp": "not_attempted",
    }


def test_completed_is_only_the_valid_ones(tmp_path: Path) -> None:
    done = _write_completed(tmp_path, seed=1)
    crashed = _write_completed(tmp_path, seed=2, is_hard_crash=True)

    ledger = LocalLedger(output_dir=tmp_path)

    assert ledger.completed([done, crashed, "never-run-exp"]) == {done}


def test_resolve_ledger_defaults_to_local(tmp_path: Path) -> None:
    done = _write_completed(tmp_path, seed=1)

    ledger = resolve_ledger(Source.local, output_dir=tmp_path)

    assert isinstance(ledger, LocalLedger)
    assert ledger.completed([done]) == {done}


def test_missing_output_dir_is_all_not_attempted(tmp_path: Path) -> None:
    ledger = LocalLedger(output_dir=tmp_path / "does-not-exist")

    assert ledger.status_for(["a", "b"]) == {"a": "not_attempted", "b": "not_attempted"}
