"""Tests for the `run_meta.json` contract stamped beside statics metrics.

The Hub call in `StaticsIdentity.resolve` is the subject here, not a seam mocked out of the way.
The failure-handling (offline/private repo records a null sha rather than crashing a completed run)
is the behaviour under test, so `HfApi` is patched to force each outcome.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Literal, cast

import datasets
import pytest

from gptnt.players.specification import PlayerCapabilities
from gptnt.provenance import Provenance
from gptnt.statics import run as statics_run, run_metadata

from tests._factories.experiments import make_provenance

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic_ai import Agent
    from pytest_mock import MockerFixture

    from gptnt.processors.image_resizer import ImageResizer
    from gptnt.statics.preprocess import PostprocessInputsFunc

type ExistingOutputState = Literal["fresh", "missing_metadata", "conflicting_metadata"]


class _StubHfApi:
    """Zero-arg stand-in for `HfApi` whose `dataset_info` raises."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def dataset_info(self, repo_id: str, *, revision: str | None = None) -> None:
        _ = repo_id, revision
        raise self._error


def _patch_hub(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setattr(run_metadata, "HfApi", lambda: _StubHfApi(error))


def test_statics_identity_records_null_sha_when_hub_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_hub(monkeypatch, OSError("offline"))
    identity = run_metadata.StaticsIdentity.resolve(
        task_name="expert_vqa", hf_repo_id="org/ds", dataset_split="test", revision="v1.0"
    )
    assert identity.resolved_revision is None
    assert identity.requested_revision == "v1.0"


def _identity(*, requested: str | None, resolved: str | None) -> run_metadata.StaticsIdentity:
    return run_metadata.StaticsIdentity(
        task_name="expert-ocr",
        hf_repo_id="org/ds",
        dataset_split=None,
        requested_revision=requested,
        resolved_revision=resolved,
    )


@pytest.mark.parametrize(
    ("state", "condition"),
    [
        ("fresh", None),
        ("missing_metadata", "run_meta.json is missing"),
        ("conflicting_metadata", "does not match the current run"),
    ],
)
def test_run_metadata_is_bound_before_predictions_and_validated_on_resume(
    tmp_path: Path, state: ExistingOutputState, condition: str | None
) -> None:
    """Write metadata for new outputs and reject unlabelled or conflicting resumed outputs."""
    metadata = run_metadata.StaticsRunMetadata.model_validate(
        {
            "model_name": "test-model",
            "run_date": "2026-08-20T10:00:00Z",
            "statics": _identity(requested="v1", resolved="a1b2c3d4e5f6"),
            "capabilities": PlayerCapabilities(player_name="test-player", player_type="ai"),
            "provenance": make_provenance(),
        }
    )

    # Arrange the output state present when a run starts or resumes.
    match state:
        case "fresh":
            pass
        case "missing_metadata":
            _ = (tmp_path / "prediction_0.json").write_text("{}")
        case "conflicting_metadata":
            stored_metadata = metadata.model_copy(
                update={
                    "provenance": metadata.provenance.model_copy(
                        update={
                            "protected_content_digest": "sha256:" + "2" * 64,
                            "protected_content_modified": True,
                        }
                    )
                }
            )
            _ = (tmp_path / "run_meta.json").write_text(stored_metadata.model_dump_json())

    if condition is not None:
        with pytest.raises(ValueError, match=condition):
            _ = run_metadata.bind_run_metadata(metadata, output_dir=tmp_path)
        return

    written_metadata = run_metadata.bind_run_metadata(metadata, output_dir=tmp_path)
    resumed_metadata = metadata.model_copy(
        update={
            "run_date": metadata.run_date.add(seconds=1),
            "statics": metadata.statics.model_copy(update={"resolved_revision": "b2c3d4e5f6a1"}),
        }
    )
    resumed_metadata = run_metadata.bind_run_metadata(resumed_metadata, output_dir=tmp_path)

    stored_metadata = run_metadata.StaticsRunMetadata.model_validate_json(
        (tmp_path / "run_meta.json").read_text()
    )
    assert written_metadata == resumed_metadata == stored_metadata == metadata


def test_revision_label_is_the_resolved_sha_not_the_requested_tag() -> None:
    """The label pins on the resolved commit sha.

    A moving tag never forms it.
    """
    identity = _identity(requested="release-2024-01", resolved="a1b2c3d4e5f6")
    assert identity.is_pinned
    assert identity.revision_label == "a1b2c3d4"
    assert identity.target == "expert-ocr@a1b2c3d4"


def test_distinct_pins_do_not_collide_on_a_shared_tag_prefix() -> None:
    """Runs whose tags share an 8-char prefix but resolve to different shas stay distinct."""
    first = _identity(requested="release-2024-01", resolved="aaaa1111deadbeef")
    second = _identity(requested="release-2024-02", resolved="bbbb2222deadbeef")
    assert first.target != second.target


def test_unpinned_when_no_resolved_sha_even_with_a_requested_tag() -> None:
    """A missing resolved commit sha (offline/private) leaves the run unpinned."""
    identity = _identity(requested="v1", resolved=None)
    assert not identity.is_pinned
    assert identity.revision_label == "unpinned"


@pytest.mark.anyio
async def test_hf_run_loads_the_resolved_revision_recorded_in_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """A resumed run loads the stored commit after its requested reference moves."""
    stored_identity = _identity(requested="moving-tag", resolved="a1b2c3d4e5f6")
    current_identity = stored_identity.model_copy(update={"resolved_revision": "b2c3d4e5f6a1"})
    stored_metadata = run_metadata.StaticsRunMetadata.model_validate(
        {
            "model_name": "test-model",
            "run_date": "2026-08-20T10:00:00Z",
            "statics": stored_identity,
            "capabilities": PlayerCapabilities(player_name="test-player", player_type="ai"),
            "provenance": make_provenance(),
        }
    )
    runner = object.__new__(statics_run.RunHFDatasetEvaluation)
    runner.model_name = "test-model"
    runner.task_name = current_identity.task_name
    runner.hf_repo_id = current_identity.hf_repo_id
    runner.dataset_split = current_identity.dataset_split
    runner.revision = current_identity.requested_revision
    runner.capabilities = stored_metadata.capabilities
    runner.max_instances = None
    runner.preprocess_instance_func = cast(
        "PostprocessInputsFunc", cast("object", mocker.Mock(return_value={"prompt": "question"}))
    )
    runner.agent = cast(
        "Agent[object, str]",
        cast(
            "object", mocker.Mock(_get_instructions=mocker.Mock(return_value=("instructions", [])))
        ),
    )
    runner.image_resizer = cast("ImageResizer", cast("object", mocker.Mock()))
    runner._resolved_revision = None
    runner.force = False

    # The Hub now resolves the moving tag to another commit, but resume returns stored metadata.
    monkeypatch.setattr(statics_run, "paths", SimpleNamespace(output=tmp_path))
    capture_provenance = mocker.patch.object(Provenance, "capture", return_value=make_provenance())
    resolve_identity = mocker.patch.object(
        run_metadata.StaticsIdentity, "resolve", return_value=current_identity
    )
    write_metadata = mocker.patch.object(
        statics_run, "bind_run_metadata", return_value=stored_metadata
    )
    skip_predictions = mocker.patch.object(
        statics_run.RunEvaluation, "throw", autospec=True, return_value=None
    )
    await runner.throw()

    # Dataset loading uses the stored commit rather than the tag's new target.
    dataset = datasets.Dataset.from_dict({"prompt": ["question"]})
    load_dataset = mocker.patch.object(datasets, "load_dataset", return_value=dataset)
    instances = runner.load_dataset()

    current_metadata = write_metadata.call_args.args[0]
    assert current_metadata.statics == current_identity
    capture_provenance.assert_called_once_with(force=False)
    resolve_identity.assert_called_once_with(
        task_name=current_identity.task_name,
        hf_repo_id=current_identity.hf_repo_id,
        dataset_split=current_identity.dataset_split,
        revision=current_identity.requested_revision,
    )
    assert write_metadata.call_args.kwargs == {
        "output_dir": tmp_path / "expert-ocr_predictions" / "test-model"
    }
    _ = skip_predictions.assert_awaited_once_with(runner)
    load_dataset.assert_called_once_with(
        stored_identity.hf_repo_id,
        split=stored_identity.dataset_split,
        revision=stored_identity.resolved_revision,
    )
    assert instances[0]["instructions"] == "instructions"
