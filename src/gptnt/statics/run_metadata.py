from typing import Self

import structlog
from huggingface_hub import HfApi
from pydantic import BaseModel, Field
from whenever import Instant

from gptnt.experiments.provenance import ProvenanceMixin
from gptnt.players.specification import PlayerCapabilities

logger = structlog.get_logger()
_UNPINNED = "unpinned"


def _resolve_commit_sha(*, hf_repo_id: str, revision: str | None) -> str | None:
    """Resolve the requested revision to a commit sha, best-effort.

    I apologise for the blanket exception. An offline or private repo must not fail a completed
    run, so any Hub error records a null sha instead of propagating. The Hub can throw a variety of
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


class DatasetIdentity(BaseModel, frozen=True):
    """What was measured: the repo, split, requested revision, and resolved commit sha."""

    hf_repo_id: str
    dataset_split: str | None
    requested_revision: str | None
    resolved_revision: str | None

    @classmethod
    def resolve(cls, *, hf_repo_id: str, dataset_split: str | None, revision: str | None) -> Self:
        """Resolve the requested revision to a commit sha, best-effort.

        The resolved sha pins what was measured. Resolving it needs the Hub, so it is
        best-effort: an offline or private repo records a null resolved sha rather than failing a
        completed run.
        """
        return cls(
            hf_repo_id=hf_repo_id,
            dataset_split=dataset_split,
            requested_revision=revision,
            resolved_revision=_resolve_commit_sha(hf_repo_id=hf_repo_id, revision=revision),
        )

    @property
    def revision_label(self) -> str:
        """A short label for the dataset revision.

        If it's not available, return a mark for an unpinned dataset.
        """
        reference = self.resolved_revision or self.requested_revision
        return reference[:8] if reference else _UNPINNED


class StaticsRunMetadata(BaseModel, frozen=True):
    """Everything a submission needs beyond the predictions."""

    task_name: str
    model_name: str
    run_date: Instant = Field(default_factory=Instant.now)
    dataset: DatasetIdentity
    capabilities: PlayerCapabilities
    provenance: ProvenanceMixin = Field(default_factory=ProvenanceMixin)
