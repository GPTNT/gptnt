"""Build the statics (HuggingFace no-game) submission: predictions + metrics + dataset identity."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from rich.console import Console

from gptnt.cli.submission._identity import finalize_manifest, is_known_model_name, slugify
from gptnt.cli.submission._io import write_predictions
from gptnt.cli.submission._schema import (
    DatasetIdentity,
    Provenance,
    StaticsSubmission,
    SystemInfo,
    capability_snapshot,
)
from gptnt.specification import PlayerCapabilities

if TYPE_CHECKING:
    from pathlib import Path

console = Console()

_UNPINNED = "unpinned"


def _read_predictions(outputs_dir: Path) -> list[dict[str, Any]]:
    """Every `prediction_{i}.json` under a statics outputs dir, index-ordered."""
    files = sorted(outputs_dir.glob("prediction_*.json"))
    if not files:
        raise RuntimeError(f"No prediction_*.json files found under {outputs_dir}")
    return [json.loads(path.read_text()) for path in files]


def _revision_label(dataset: DatasetIdentity) -> str:
    """A short folder label: the resolved sha, else the requested ref, else an unpinned mark."""
    reference = dataset.resolved_revision or dataset.requested_revision
    return reference[:8] if reference else _UNPINNED


def _assemble_manifest(
    meta: dict[str, Any], metrics: dict[str, Any], task: str
) -> StaticsSubmission:
    """Build the statics `submission.yaml` model from the stamped run metadata and metrics."""
    capabilities = PlayerCapabilities.model_validate(meta["capabilities"])
    system = SystemInfo(model=capabilities.player_name)
    if not is_known_model_name(system.model):
        console.print(
            f"[yellow]Model name {system.model!r} is not a known pydantic-ai id "
            "(expected for an open/HuggingFace checkpoint)."
        )

    dataset = DatasetIdentity.model_validate(meta["dataset"])
    run_date = meta["run_date"][:10]
    capfp = capabilities.fingerprint[:8]
    return StaticsSubmission(
        submission_id=f"{run_date}_{slugify(system.model)}_{task}@{_revision_label(dataset)}_{capfp}",
        system=system,
        capabilities={
            "player": capability_snapshot(
                capabilities.fingerprint, capabilities.model_dump(mode="json")
            )
        },
        dataset=dataset,
        provenance=Provenance(
            gptnt_version=meta["provenance"]["gptnt_version"],
            git_sha=meta["provenance"]["git_sha"],
            run_date=run_date,
        ),
        metrics=metrics,
    )


def build_statics_submission(outputs_dir: Path, static_task: str | None, into: Path) -> Path:
    """Build one statics submission bundle and return its directory."""
    meta_path = outputs_dir / "run_meta.json"
    metrics_path = outputs_dir / "metrics.json"
    if not meta_path.exists() or not metrics_path.exists():
        raise RuntimeError(
            f"{outputs_dir} is not a statics outputs dir (needs run_meta.json and metrics.json); "
            "run `gptnt statics <task> --throw --dataset-revision <ref>` first."
        )

    meta = json.loads(meta_path.read_text())
    task = static_task or meta["task_name"]
    manifest = _assemble_manifest(meta, json.loads(metrics_path.read_text()), task)
    capfp = manifest.capabilities["player"]["fingerprint"][:8]
    bundle_dir = (
        into
        / slugify(manifest.system.model)
        / f"{task}@{_revision_label(manifest.dataset)}_{capfp}"
    )

    bundle_dir.mkdir(parents=True, exist_ok=True)
    write_predictions(bundle_dir / "predictions.parquet", _read_predictions(outputs_dir))
    _ = (bundle_dir / "metrics.json").write_text(metrics_path.read_text())
    finalize_manifest(bundle_dir, manifest)
    console.print(f"[bold green]Wrote submission bundle:[/bold green] {bundle_dir}")
    return bundle_dir
