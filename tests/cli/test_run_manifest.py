"""Tests for the `run.yaml` manifest schema and loader.

This is the deterministic, infra-free surface: the pydantic schema (defaults, constraints, and the
`extra="forbid"` gates) and the loader's error handling. No network, no Hydra, no config-name
cross-checks (those belong to `gptnt doctor <run.yaml>`, a later chunk).
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
import yaml
from pydantic import ValidationError

from gptnt.cli.run.manifest import RunManifest
from gptnt.experiments.ledger.base import Source

# tests/cli/test_run_manifest.py -> tests/cli -> tests -> <repo root>
_REPO_ROOT = Path(__file__).resolve().parents[2]
_QUICKSTART = _REPO_ROOT / "runs" / "quickstart.yaml"


def _minimal_manifest() -> dict[str, object]:
    """Return the smallest valid manifest payload (everything else defaults)."""
    return {
        "suites": ["single-pairwise-sync"],
        "rooms": 2,
        "players": [{"model": "claude46"}, {"model": "gemini-3"}],
    }


def _load_payload(tmp_path: Path, payload: dict[str, object]) -> RunManifest:
    """Write `payload` to a file and load it through the real `RunManifest.from_path` entrypoint.

    Structural errors propagate as pydantic's own `ValidationError` (the loader no longer wraps
    them); the negative cases assert on that directly.
    """
    manifest_file = tmp_path / "run.yaml"
    _ = manifest_file.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return RunManifest.from_path(manifest_file)


def test_default_models_do_not_share_mutable_state() -> None:
    """`Field(default_factory=...)` must give each manifest its own nested models."""
    first = RunManifest.model_validate(_minimal_manifest())
    second = RunManifest.model_validate(_minimal_manifest())

    first.anchors.best_expert = "claude46"

    assert first.anchors.best_expert == "claude46"
    assert second.anchors.best_expert is None


def test_loads_manifest_from_yaml_file(tmp_path: Path) -> None:
    spec = """
        spec_version: 2
        suites: [single-pairwise-sync]
        rooms: 3
        players:
          - model: claude46
        anchors:
          best_expert: claude46
        """
    manifest_file = tmp_path / "run.yaml"
    _ = manifest_file.write_text(dedent(spec), encoding="utf-8")

    manifest = RunManifest.from_path(manifest_file)

    assert manifest.rooms == 3
    assert manifest.players[0].model == "claude46"
    assert manifest.anchors.best_expert == "claude46"


def test_committed_quickstart_manifest_loads_cleanly() -> None:
    assert _QUICKSTART.exists(), f"expected example manifest at {_QUICKSTART}"

    manifest = RunManifest.from_path(_QUICKSTART)

    assert manifest.spec_version == 2
    assert manifest.suites == ["single-pairwise-sync"]
    assert manifest.rooms == 2
    assert [player.model for player in manifest.players] == ["test_defuser", "test_expert"]
    assert manifest.anchors.best_expert is None
    assert manifest.source is Source.local


def test_unknown_top_level_key_is_rejected(tmp_path: Path) -> None:
    payload = _minimal_manifest()
    payload["roomz"] = 2  # typo'd `rooms`

    with pytest.raises(ValidationError):
        _ = _load_payload(tmp_path, payload)


def test_unknown_nested_player_key_is_rejected(tmp_path: Path) -> None:
    payload = _minimal_manifest()
    payload["players"] = [{"model": "claude46", "kount": 2}]  # typo'd `count`

    with pytest.raises(ValidationError):
        _ = _load_payload(tmp_path, payload)


def test_unsupported_spec_version_is_rejected(tmp_path: Path) -> None:
    payload = _minimal_manifest()
    payload["spec_version"] = 1  # the superseded schema

    with pytest.raises(ValidationError):
        _ = _load_payload(tmp_path, payload)


def test_empty_suites_is_rejected(tmp_path: Path) -> None:
    payload = _minimal_manifest()
    payload["suites"] = []

    with pytest.raises(ValidationError):
        _ = _load_payload(tmp_path, payload)


def test_zero_rooms_is_rejected(tmp_path: Path) -> None:
    payload = _minimal_manifest()
    payload["rooms"] = 0

    with pytest.raises(ValidationError):
        _ = _load_payload(tmp_path, payload)


def test_displays_defaults_to_none(tmp_path: Path) -> None:
    """Omitting `displays` means 'inherit the ambient $DISPLAY', represented as None."""
    manifest = _load_payload(tmp_path, _minimal_manifest())

    assert manifest.displays is None


def test_displays_accepts_explicit_list(tmp_path: Path) -> None:
    payload = _minimal_manifest()
    payload["displays"] = [0, 1]

    manifest = _load_payload(tmp_path, payload)

    assert manifest.displays == [0, 1]


def test_empty_displays_list_is_rejected(tmp_path: Path) -> None:
    """An explicit empty list is meaningless; `min_length=1` rejects it (use omission for
    default)."""
    payload = _minimal_manifest()
    payload["displays"] = []

    with pytest.raises(ValidationError):
        _ = _load_payload(tmp_path, payload)


def test_negative_display_number_is_rejected(tmp_path: Path) -> None:
    payload = _minimal_manifest()
    payload["displays"] = [0, -1]

    with pytest.raises(ValidationError):
        _ = _load_payload(tmp_path, payload)


def test_recording_key_is_rejected(tmp_path: Path) -> None:
    """The recorder output location is env-driven (`EXPERIMENT_RECORDER_OUTPUTS`), not a manifest
    key, so any `recording:` block is rejected by `extra='forbid'`."""
    payload = _minimal_manifest()
    payload["recording"] = {"output_dir": "somewhere"}

    with pytest.raises(ValidationError):
        _ = _load_payload(tmp_path, payload)


@pytest.mark.parametrize("source_value", ["local", "wandb"])
def test_source_accepts_local_and_wandb(tmp_path: Path, source_value: str) -> None:
    payload = _minimal_manifest()
    payload["source"] = source_value

    manifest = _load_payload(tmp_path, payload)

    assert manifest.source == Source(source_value)


def test_missing_file_propagates_filenotfound(tmp_path: Path) -> None:
    """Path existence is the CLI's job (Typer's `exists=True`); `RunManifest.from_path` no longer
    wraps it.

    Called directly on a missing path, it surfaces Python's own `FileNotFoundError` rather than a
    bespoke manifest error.
    """
    missing = tmp_path / "does-not-exist.yaml"

    with pytest.raises(FileNotFoundError):
        _ = RunManifest.from_path(missing)
