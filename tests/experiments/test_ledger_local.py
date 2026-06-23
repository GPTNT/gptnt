"""The on-disk completion ledger, exercised against real recorded outputs.

The local ledger is what makes the benchmark runnable without W&B, so these tests pin the actual
disk → status mapping: a solved or cleanly-lost experiment is `done`, a crashed or abandoned one is
`failed`, and an experiment with no output is `not_attempted`. Real `BombState` objects drive the
validity check (the same one the DB ingestion uses), not stubs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import orjson

from gptnt.experiments.ledger.base import Source
from gptnt.experiments.ledger.local import LocalLedger
from gptnt.experiments.ledger.resolve import resolve_ledger
from gptnt.ktane.state.bomb import BombState

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


def _write_completed(output_dir: Path, attempt_name: str, *, is_hard_crash: bool = False) -> None:
    """Write a recorded output that reached a final (completed) bomb state."""
    payload = {
        "is_hard_crash": is_hard_crash,
        "step_records": [
            {"bomb_state": _completed_bomb_state().model_dump(mode="json", by_alias=True)}
        ],
    }
    _write(output_dir, attempt_name, payload)


def _write_never_completed(output_dir: Path, attempt_name: str) -> None:
    """Write a recorded output that never reached a bomb state (crashed before the first step)."""
    _write(
        output_dir, attempt_name, {"is_hard_crash": False, "step_records": [{"bomb_state": None}]}
    )


def _write(output_dir: Path, attempt_name: str, payload: dict[str, object]) -> None:
    path = output_dir / f"experiment-{attempt_name}-{uuid4()}.json"
    _ = path.write_bytes(orjson.dumps(payload))


def test_status_for_classifies_each_outcome(tmp_path: Path) -> None:
    _write_completed(tmp_path, "done-exp")
    _write_completed(tmp_path, "crashed-exp", is_hard_crash=True)
    _write_never_completed(tmp_path, "incomplete-exp")

    ledger = LocalLedger(output_dir=tmp_path)
    statuses = ledger.status_for(["done-exp", "crashed-exp", "incomplete-exp", "never-run-exp"])

    assert statuses == {
        "done-exp": "done",
        "crashed-exp": "failed",  # a hard crash is never valid, even with a final bomb state
        "incomplete-exp": "failed",  # never reached a final bomb state
        "never-run-exp": "not_attempted",
    }


def test_completed_is_only_the_valid_ones(tmp_path: Path) -> None:
    _write_completed(tmp_path, "done-exp")
    _write_completed(tmp_path, "crashed-exp", is_hard_crash=True)

    ledger = LocalLedger(output_dir=tmp_path)

    assert ledger.completed(["done-exp", "crashed-exp", "never-run-exp"]) == {"done-exp"}


def test_resolve_ledger_defaults_to_local(tmp_path: Path) -> None:
    _write_completed(tmp_path, "done-exp")

    ledger = resolve_ledger(Source.local, output_dir=tmp_path)

    assert isinstance(ledger, LocalLedger)
    assert ledger.completed(["done-exp"]) == {"done-exp"}


def test_missing_output_dir_is_all_not_attempted(tmp_path: Path) -> None:
    ledger = LocalLedger(output_dir=tmp_path / "does-not-exist")

    assert ledger.status_for(["a", "b"]) == {"a": "not_attempted", "b": "not_attempted"}
