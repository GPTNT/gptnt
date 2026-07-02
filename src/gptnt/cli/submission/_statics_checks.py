"""The deterministic checks behind `submission validate` for a statics bundle."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gptnt.cli.doctor.checks import CheckResult
from gptnt.cli.submission._checks import check_provenance
from gptnt.cli.submission._io import read_predictions
from gptnt.cli.submission._schema import StaticsSubmission
from gptnt.specification import PlayerCapabilities

if TYPE_CHECKING:
    from pathlib import Path


def _check_identity(manifest: StaticsSubmission) -> CheckResult:
    """Model name matches the capabilities, and the capability fingerprint reconstructs."""
    player = manifest.capabilities["player"]
    if manifest.system.model != player["player_name"]:
        return CheckResult(
            "identity", "fail", "system.model does not match the capabilities player_name"
        )

    stated = player.get("fingerprint")
    reconstructable = {key: setting for key, setting in player.items() if key != "fingerprint"}
    if PlayerCapabilities.model_validate(reconstructable).fingerprint != stated:
        return CheckResult("identity", "fail", "capability fingerprint is inconsistent")

    if not manifest.system.provider or not manifest.system.organization:
        return CheckResult(
            "identity",
            "warn",
            "provider/organization not declared",
            "fill in system.provider and system.organization in submission.yaml.",
        )
    return CheckResult(
        "identity", "pass", f"model {manifest.system.model!r} and fingerprint agree"
    )


def _check_dataset(manifest: StaticsSubmission) -> CheckResult:
    """The dataset must be pinned to a revision, so 'what was measured' is frozen."""
    dataset = manifest.dataset
    if dataset.resolved_revision is None and dataset.requested_revision is None:
        return CheckResult(
            "dataset",
            "warn",
            f"{dataset.hf_repo_id} is not pinned to a revision",
            "re-run with `--dataset-revision <sha>` so the measurement is reproducible.",
        )
    pinned = dataset.resolved_revision or dataset.requested_revision
    return CheckResult("dataset", "pass", f"{dataset.hf_repo_id} pinned at {pinned}")


def _check_predictions(bundle_dir: Path, manifest: StaticsSubmission) -> CheckResult:
    """Predictions and metrics must both be present and non-empty."""
    predictions = read_predictions(bundle_dir / "predictions.parquet")
    if not predictions:
        return CheckResult("predictions", "fail", "predictions.parquet is empty")
    if not manifest.metrics:
        return CheckResult("predictions", "fail", "metrics are empty")
    return CheckResult("predictions", "pass", f"{len(predictions)} predictions, metrics present")


def _check_recompute() -> CheckResult:
    """Re-scoring the predictions against the pinned dataset is a documented follow-up.

    It needs a network fetch of the dataset plus a task -> scorer registry the command modules do
    not yet expose. Marked `skip` (never fails) until that registry lands.
    """
    return CheckResult(
        "recompute", "skip", "metric recompute against the dataset not yet implemented"
    )


def statics_checks(bundle_dir: Path, manifest_data: dict[str, Any]) -> list[CheckResult]:
    """Run every statics check and return the findings in report order."""
    manifest = StaticsSubmission.model_validate(manifest_data)
    return [
        _check_identity(manifest),
        _check_dataset(manifest),
        _check_predictions(bundle_dir, manifest),
        check_provenance(manifest.provenance),
        _check_recompute(),
    ]
