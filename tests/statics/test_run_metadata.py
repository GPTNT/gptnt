"""Tests for the `run_meta.json` contract stamped beside statics metrics.

The Hub call in `StaticsIdentity.resolve` is the subject here, not a seam mocked out of the way.
The failure-handling (offline/private repo records a null sha rather than crashing a completed run)
is the behaviour under test, so `HfApi` is patched to force each outcome.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from whenever import Instant

from gptnt.experiments.provenance import ProvenanceMixin
from gptnt.players.specification import PlayerCapabilities
from gptnt.statics import run_metadata


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


def test_statics_identity_records_null_sha_when_hub_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_hub(monkeypatch, error=OSError("offline"))
    identity = run_metadata.StaticsIdentity.resolve(
        task_name="expert_vqa", hf_repo_id="org/ds", dataset_split="test", revision="v1.0"
    )
    assert identity.resolved_revision is None
    assert identity.requested_revision == "v1.0"


def test_statics_identity_records_resolved_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_hub(monkeypatch, sha="notyourrun")
    assert (
        run_metadata.StaticsIdentity.resolve(
            task_name="expert_vqa", hf_repo_id="org/ds", dataset_split=None, revision="main"
        ).resolved_revision
        == "notyourrun"
    )


def test_run_metadata_stamps_provenance_and_round_trips(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_hub(monkeypatch, sha="notyourrun")
    capabilities = PlayerCapabilities(player_name="test-player", player_type="ai")
    metadata = run_metadata.StaticsRunMetadata(
        model_name="test-model",
        run_date=Instant.now(),
        statics=run_metadata.StaticsIdentity.resolve(
            task_name="expert_vqa", hf_repo_id="org/ds", dataset_split="test", revision="v1.0"
        ),
        capabilities=capabilities,
        provenance=ProvenanceMixin(),
    )
    assert metadata.statics.resolved_revision == "notyourrun"
    assert metadata.statics.requested_revision == "v1.0"
    assert metadata.capabilities == capabilities
    assert metadata.provenance.gptnt_version
    assert (
        run_metadata.StaticsRunMetadata.model_validate_json(metadata.model_dump_json()) == metadata
    )


def test_missing_provenance_or_run_date_is_rejected() -> None:
    """A `run_meta.json` lacking provenance/run_date must fail, not silently backfill from here."""
    statics = run_metadata.StaticsIdentity(
        task_name="t",
        hf_repo_id="org/ds",
        dataset_split=None,
        requested_revision="v1",
        resolved_revision="a1b2c3d4e5f6",
    )
    capabilities = PlayerCapabilities(player_name="p", player_type="ai")
    partial_run_meta = {
        "model_name": "m",
        "statics": statics.model_dump(),
        "capabilities": capabilities.model_dump(mode="json"),
    }
    with pytest.raises(ValidationError):
        _ = run_metadata.StaticsRunMetadata.model_validate(partial_run_meta)


def _identity(*, requested: str | None, resolved: str | None) -> run_metadata.StaticsIdentity:
    return run_metadata.StaticsIdentity(
        task_name="expert-ocr",
        hf_repo_id="org/ds",
        dataset_split=None,
        requested_revision=requested,
        resolved_revision=resolved,
    )


def test_revision_label_is_the_resolved_sha_not_the_requested_tag() -> None:
    """The label pins on the resolved commit sha; a moving tag never forms it."""
    identity = _identity(requested="release-2024-01", resolved="a1b2c3d4e5f6")
    assert identity.is_pinned
    assert identity.revision_label == "a1b2c3d4"
    assert identity.target == "expert-ocr@a1b2c3d4"


def test_distinct_pins_do_not_collide_on_a_shared_tag_prefix() -> None:
    """Two runs whose tags share an 8-char prefix but resolve to different shas stay distinct."""
    first = _identity(requested="release-2024-01", resolved="aaaa1111deadbeef")
    second = _identity(requested="release-2024-02", resolved="bbbb2222deadbeef")
    assert first.target != second.target


def test_unpinned_when_no_resolved_sha_even_with_a_requested_tag() -> None:
    """No resolved commit sha (offline/private) means unpinned — never the requested tag."""
    identity = _identity(requested="v1", resolved=None)
    assert not identity.is_pinned
    assert identity.revision_label == "unpinned"
