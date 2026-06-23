"""The W&B-optional commands, exercised through the CLI runner with the local source.

These pin the user-visible behaviour that makes the benchmark runnable without a W&B account:
`status` reports completion from disk, `submit` skips already-done specs from disk, and
`cleanup-outputs` prunes invalid local files. They run with no W&B configured.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import orjson

from gptnt.cli.__main__ import build_app
from gptnt.core.ktane.mission_spec import KtaneMissionSpec
from gptnt.core.ktane.state.bomb import BombState
from gptnt.core.specification import PlayerProtocol
from gptnt.experiments.ledger.base import Source
from gptnt.experiments.ledger.resolve import filter_experiments
from gptnt.experiments.spec import ExperimentSpec

from tests._cli_runner import invoke_cli

if TYPE_CHECKING:
    from pathlib import Path


def _spec(seed: int) -> ExperimentSpec:
    """A real single-player ExperimentSpec; the seed makes each attempt_name distinct."""
    return ExperimentSpec(
        mission_spec=KtaneMissionSpec(
            seed=seed,
            time_limit=300,
            num_strikes_allowed=3,
            components=["Wires"],
            optional_widgets=1,
            needy_time=60,
        ),
        condition="single_module",
        defuser_protocol=PlayerProtocol(
            role="defuser",
            communication_style="sync",
            is_playing_alone=True,
            include_manual=False,
            receive_feedback_after_action=False,
            allow_magic_actions=False,
        ),
        defuser_name="test-defuser",
        expert_protocol=None,
        expert_name=None,
    )


def _write_completed_output(output_dir: Path, attempt_name: str) -> None:
    """Write a recorded output that reached a valid, completed bomb state."""
    bomb_state = BombState.model_validate(
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
            "modules": [],
        }
    )
    payload = {
        "is_hard_crash": False,
        "step_records": [{"bomb_state": bomb_state.model_dump(mode="json", by_alias=True)}],
    }
    path = output_dir / f"experiment-{attempt_name}-{uuid4()}.json"
    _ = path.write_bytes(orjson.dumps(payload))


def test_filter_experiments_drops_only_the_done_ones(tmp_path: Path) -> None:
    done, todo = _spec(1), _spec(2)
    _write_completed_output(tmp_path, done.attempt_name)

    remaining = filter_experiments([done, todo], source=Source.local, output_dir=tmp_path)

    assert remaining == [todo]


def test_status_reports_disk_completion(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    _write_completed_output(output_dir, "done-exp")

    # The status command reads its "expected" names from a dir of `<attempt_name>.json` files.
    expected_dir = tmp_path / "expected"
    expected_dir.mkdir()
    for name in ("done-exp", "todo-exp"):
        _ = (expected_dir / f"{name}.json").write_text("{}")

    result = invoke_cli(
        build_app(), ["status", str(expected_dir), "--output-dir", str(output_dir)]
    )

    assert result.exit_code == 0, result.output
    assert "done-exp" in result.output
    assert "1 done" in result.output
    assert "1 not attempted" in result.output


def test_cleanup_local_prunes_invalid_outputs(tmp_path: Path) -> None:
    _write_completed_output(tmp_path, "keep-exp")
    crashed = tmp_path / f"experiment-drop-exp-{uuid4()}.json"
    _ = crashed.write_bytes(
        orjson.dumps({"is_hard_crash": True, "step_records": [{"bomb_state": None}]})
    )

    result = invoke_cli(build_app(), ["cleanup-outputs", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert not crashed.exists()
    assert list(tmp_path.glob("experiment-keep-exp-*.json"))
