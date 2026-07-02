"""Model identity and attribution for a submission.

The canonical, provider-less model name is already recorded as each side's `player_name`, so it is
read straight off the records — no config re-composition. The provider, organisation and open
weights flag cannot be derived (an open checkpoint served behind an OpenAI-compatible endpoint
reports provider `openai`), so they are submitter-declared and preserved across re-runs.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from pydantic_ai.models import known_model_names

from gptnt.cli.submission._io import read_yaml, write_yaml
from gptnt.cli.submission._schema import (
    InteractiveSubmission,
    StaticsSubmission,
    SystemInfo,
    capability_snapshot,
)

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.experiments.descriptor import ExperimentDescriptor
    from gptnt.specification import PlayerCapabilities


def slugify(name: str) -> str:
    """Lowercase, and collapse any run of non-`[a-z0-9]` into one dash (dots become dashes)."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def is_known_model_name(name: str) -> bool:
    """Whether pydantic-ai recognises the name (open/HF checkpoints are absent by design)."""
    return name in set(known_model_names())


def _side_snapshot(capabilities: PlayerCapabilities) -> dict[str, Any]:
    """A reconstructable capability block for one side: the full dump plus its fingerprint."""
    return capability_snapshot(capabilities.fingerprint, capabilities.model_dump(mode="json"))


def build_capabilities_block(descriptor: ExperimentDescriptor) -> dict[str, Any]:
    """The `capabilities` manifest block: a snapshot per side (expert omitted for solo play)."""
    block: dict[str, Any] = {"defuser": _side_snapshot(descriptor.defuser_capabilities)}
    if descriptor.expert_capabilities is not None:
        block["expert"] = _side_snapshot(descriptor.expert_capabilities)
    return block


def build_system_info(descriptor: ExperimentDescriptor) -> SystemInfo:
    """Derive the `system` block's model name(s) from the recorded capabilities.

    `expert_model` is set only when the expert is a different model (a mixed-model pairwise suite).
    """
    defuser_model = descriptor.defuser_capabilities.player_name
    expert_capabilities = descriptor.expert_capabilities
    if expert_capabilities is None:
        return SystemInfo(model=defuser_model)

    expert_model = expert_capabilities.player_name
    if expert_model == defuser_model:
        return SystemInfo(model=defuser_model)
    return SystemInfo(model=defuser_model, expert_model=expert_model)


def merge_preserved[Submission: (InteractiveSubmission, StaticsSubmission)](
    generated: Submission, existing: dict[str, Any] | None
) -> Submission:
    """Overwrite the `[auto]` fields, preserve the submitter and declared attribution.

    On a re-run the derived identity, capabilities, dataset/suite, provenance and stats/metrics are
    regenerated, but the submitter block and the declared `system` fields (provider, organisation,
    is-os, type, description url) the submitter filled in are kept.
    """
    if existing is None:
        return generated

    preserved_system = existing.get("system", {})
    system = generated.system.model_copy(
        update={
            field: preserved_system[field]
            for field in ("provider", "organization", "is_os_model", "type", "description_url")
            if field in preserved_system
        }
    )
    return generated.model_copy(
        update={
            "submitter": existing.get("submitter", generated.submitter.model_dump()),
            "system": system,
        }
    )


def finalize_manifest[Submission: (InteractiveSubmission, StaticsSubmission)](
    bundle_dir: Path, manifest: Submission
) -> None:
    """Merge preserved fields over any existing manifest, then write `submission.yaml`."""
    manifest_path = bundle_dir / "submission.yaml"
    existing = read_yaml(manifest_path) if manifest_path.exists() else None
    write_yaml(manifest_path, merge_preserved(manifest, existing).model_dump(mode="json"))
