from pathlib import Path
from typing import Self

import structlog
from huggingface_hub import HfApi
from pydantic import BaseModel
from whenever import Instant

from gptnt.players.specification import PlayerCapabilities
from gptnt.provenance import Provenance

logger = structlog.get_logger()
_UNPINNED = "unpinned"


def _resolve_commit_sha(*, hf_repo_id: str, revision: str | None) -> str | None:
    """Resolve the requested revision to a commit sha, best-effort.

    I apologise for the blanket exception. An offline or private repo must not fail a completed
    run, so any Hub error records a null sha instead of propagating. The Hub can throw several
    exceptions and we don't really care _why_ it failed, we just want to record that it did.
    """
    try:
        resolved = HfApi().dataset_info(hf_repo_id, revision=revision).sha
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Could not resolve dataset commit sha",
            hf_repo_id=hf_repo_id,
            revision=revision,
            error=str(exc),
        )
        return None
    if not resolved:
        logger.warning("Hub returned no commit sha", hf_repo_id=hf_repo_id, revision=revision)
        return None
    return resolved


class StaticsIdentity(BaseModel, frozen=True):
    """What was measured: the task plus its dataset pin (repo, split, revisions)."""

    task_name: str
    hf_repo_id: str
    dataset_split: str | None
    requested_revision: str | None
    resolved_revision: str | None

    @classmethod
    def resolve(
        cls, *, task_name: str, hf_repo_id: str, dataset_split: str | None, revision: str | None
    ) -> Self:
        """Resolve the requested revision to a commit sha, best-effort.

        The resolved sha pins what was measured. Resolving it needs the Hub, so it is
        best-effort: an offline or private repo records a null resolved sha rather than failing a
        completed run.
        """
        return cls(
            task_name=task_name,
            hf_repo_id=hf_repo_id,
            dataset_split=dataset_split,
            requested_revision=revision,
            resolved_revision=_resolve_commit_sha(hf_repo_id=hf_repo_id, revision=revision),
        )

    @property
    def is_pinned(self) -> bool:
        """Whether the dataset is pinned to a concrete commit (a resolved sha exists)."""
        return self.resolved_revision is not None

    @property
    def revision_label(self) -> str:
        """A short label for the dataset revision, always the resolved commit sha.

        A HuggingFace dataset is only reproducibly pinned by its commit sha; a requested tag or
        branch can move, so it never forms the label. With no resolved sha (offline/private repo),
        return the unpinned mark.
        """
        return self.resolved_revision[:8] if self.resolved_revision else _UNPINNED

    @property
    def target(self) -> str:
        """What was measured, with its pin, a submission bundle dir's leaf name."""
        return f"{self.task_name}@{self.revision_label}"


class StaticsRunMetadata(BaseModel, frozen=True):
    """Everything a submission needs beyond the predictions."""

    model_name: str
    run_date: Instant
    statics: StaticsIdentity
    capabilities: PlayerCapabilities
    provenance: Provenance


def bind_run_metadata(metadata: StaticsRunMetadata, *, output_dir: Path) -> StaticsRunMetadata:
    """Bind an output directory to its first matching metadata snapshot."""
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_file = output_dir / "run_meta.json"

    # A resumed output set retains the metadata and timestamp written before its first prediction.
    if metadata_file.exists():
        stored_metadata = StaticsRunMetadata.model_validate_json(metadata_file.read_text())
        expected_metadata = metadata.model_copy(
            update={
                "run_date": stored_metadata.run_date,
                "statics": metadata.statics.model_copy(
                    update={"resolved_revision": stored_metadata.statics.resolved_revision}
                ),
            }
        )
        if stored_metadata != expected_metadata:
            raise ValueError(
                f"Stored statics metadata at {metadata_file} does not match the current run"
            )
        return stored_metadata

    # Existing predictions cannot be assigned provenance from a later invocation.
    if any(output_dir.glob("prediction_*.json")):
        raise ValueError(
            f"Cannot resume statics outputs from {output_dir}: {metadata_file.name} is missing"
        )

    _ = metadata_file.write_text(metadata.model_dump_json(indent=2))
    return metadata
