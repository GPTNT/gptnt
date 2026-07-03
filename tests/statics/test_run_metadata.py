"""Tests for the `run_meta.json` contract stamped beside statics metrics.

The Hub call in `DatasetIdentity.resolve` is the subject here, not a seam mocked out of the way.
The failure-handling (offline/private repo records a null sha rather than crashing a completed run)
is the behaviour under test, so `HfApi` is patched to force each outcome.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gptnt.specification import PlayerCapabilities
from gptnt.statics import run_metadata

if TYPE_CHECKING:
    import pytest


class _StubDatasetInfo:
    def __init__(self, sha: str | None) -> None:
        self.sha = sha


class _StubHfApi:
    """Zero-arg stand-in for `HfApi` whose `dataset_info` returns a fixed sha or raises."""

    def __init__(self, *, sha: str | None, error: Exception | None) -> None:
        self._sha = sha
        self._error = error
        self.asked: dict[str, str | None] = {}

    def dataset_info(self, repo_id: str, *, revision: str | None = None) -> _StubDatasetInfo:
        self.asked = {"repo_id": repo_id, "revision": revision}
        if self._error is not None:
            raise self._error
        return _StubDatasetInfo(self._sha)


def _patch_hub(
    monkeypatch: pytest.MonkeyPatch, *, sha: str | None = None, error: Exception | None = None
) -> None:
    monkeypatch.setattr(run_metadata, "HfApi", lambda: _StubHfApi(sha=sha, error=error))


def test_dataset_identity_records_null_sha_when_hub_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_hub(monkeypatch, error=OSError("offline"))
    identity = run_metadata.DatasetIdentity.resolve(
        hf_repo_id="org/ds", dataset_split="test", revision="v1.0"
    )
    assert identity.resolved_revision is None
    assert identity.requested_revision == "v1.0"


def test_dataset_identity_records_resolved_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_hub(monkeypatch, sha="notyourrun")
    assert (
        run_metadata.DatasetIdentity.resolve(
            hf_repo_id="org/ds", dataset_split=None, revision="main"
        ).resolved_revision
        == "notyourrun"
    )


def test_run_metadata_build_stamps_provenance_and_round_trips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_hub(monkeypatch, sha="notyourrun")
    capabilities = PlayerCapabilities(player_name="test-player", player_type="ai")
    metadata = run_metadata.StaticsRunMetadata.build(
        task_name="expert_vqa",
        model_name="test-model",
        hf_repo_id="org/ds",
        dataset_split="test",
        revision="v1.0",
        capabilities=capabilities,
    )
    assert metadata.dataset.resolved_revision == "notyourrun"
    assert metadata.dataset.requested_revision == "v1.0"
    assert metadata.capabilities == capabilities
    assert metadata.provenance.gptnt_version
    assert (
        run_metadata.StaticsRunMetadata.model_validate_json(metadata.model_dump_json()) == metadata
    )
