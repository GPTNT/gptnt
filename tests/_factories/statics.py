"""Factory for on-disk statics run outputs (a `<task>_predictions/<model>/` dir)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from gptnt.players.specification import PlayerCapabilities

if TYPE_CHECKING:
    from pathlib import Path

_DEFAULT_METRICS: dict[str, Any] = {"module": {"total": 0.87}}


def write_statics_run(
    root: Path,
    *,
    task: str = "expert-ocr",
    model_dir: str = "gpt-5-2",
    player_name: str = "gpt-5-2",
    hf_repo_id: str = "GPTNT/expert-element-ocr",
    requested_revision: str | None = "v1",
    resolved_revision: str | None = "a1b2c3d4e5f6",
    metrics: dict[str, Any] | None = None,
) -> Path:
    """Write a statics outputs dir (metrics.json + a stamped run_meta.json); return the run dir.

    `model_dir` is the run directory leaf (the resolved model string, as the real writer names it);
    `player_name` is the config/leaderboard name — the two are distinct on purpose so tests can
    exercise the `--model` filter, which keys on `player_name`.
    """
    out = root / f"{task}_predictions" / model_dir
    out.mkdir(parents=True)
    capabilities = PlayerCapabilities(player_name=player_name, player_type="ai")
    _ = (out / "run_meta.json").write_text(
        json.dumps(
            {
                "model_name": model_dir,
                "run_date": "2026-07-02T10:00:00Z",
                "statics": {
                    "task_name": task,
                    "hf_repo_id": hf_repo_id,
                    "dataset_split": None,
                    "requested_revision": requested_revision,
                    "resolved_revision": resolved_revision,
                },
                "capabilities": capabilities.model_dump(mode="json"),
                "provenance": {"gptnt_version": "0.15.0", "git_sha": "a1b2c3d4"},
            }
        )
    )
    _ = (out / "metrics.json").write_text(json.dumps(metrics or _DEFAULT_METRICS))
    return out
