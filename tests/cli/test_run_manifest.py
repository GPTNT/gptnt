"""Tests for the `run.yaml` manifest schema and loader.

This is the deterministic, infra-free surface: the pydantic schema (defaults, constraints, and the
`extra="forbid"` gates) and the loader's error handling. No network, no Hydra, no config-name
cross-checks (those belong to `gptnt doctor <run.yaml>`, a later chunk).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from gptnt.cli.run.manifest import RunManifest
from gptnt.experiments.ledger.completion import Source

# tests/cli/test_run_manifest.py -> tests/cli -> tests -> <repo root>
_REPO_ROOT = Path(__file__).resolve().parents[2]
_QUICKSTART = _REPO_ROOT / "runs" / "quickstart.yaml"


def _minimal_manifest() -> dict[str, object]:
    """Return the smallest valid manifest payload (everything else defaults)."""
    return {
        "suites": ["single-pairwise-sync"],
        "rooms": 2,
        "players": [{"player": "claude-sonnet-4-6"}, {"player": "gemini-3-flash-preview"}],
    }


def _load_payload(tmp_path: Path, payload: dict[str, object]) -> RunManifest:
    """Write `payload` to a file and load it through the real `RunManifest.from_path` entrypoint.

    Structural errors propagate as pydantic's own `ValidationError` (the loader no longer wraps
    them). The negative cases assert on that directly.
    """
    manifest_file = tmp_path / "run.yaml"
    _ = manifest_file.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return RunManifest.from_path(manifest_file)


def test_committed_quickstart_manifest_loads_cleanly() -> None:
    assert _QUICKSTART.exists(), f"expected example manifest at {_QUICKSTART}"

    manifest = RunManifest.from_path(_QUICKSTART)

    assert manifest.spec_version == 2
    assert manifest.suites == ["single-pairwise-sync"]
    assert manifest.rooms == 2
    assert [player.player for player in manifest.players] == ["test-defuser", "test-expert"]
    assert manifest.anchors.best_expert is None
    assert manifest.source is Source.local


def test_unsupported_spec_version_is_rejected(tmp_path: Path) -> None:
    payload = _minimal_manifest()
    payload["spec_version"] = 1  # the superseded schema

    with pytest.raises(ValidationError):
        _ = _load_payload(tmp_path, payload)
