from pathlib import Path

from gptnt.cli.submission._bundle import BundleName, create_submission_player_entry, write_bundle
from gptnt.cli.submission._schema import StaticsSubmission, Submitter
from gptnt.statics.run_metadata import StaticsRunMetadata


def build_statics_submission(outputs_dir: Path, task: str, into: Path) -> Path:
    """Build one statics submission bundle (submission.yaml + metrics.json) and return its dir."""
    meta_path = outputs_dir / "run_meta.json"
    metrics_path = outputs_dir / "metrics.json"
    if not meta_path.exists() or not metrics_path.exists():
        raise RuntimeError(
            f"{outputs_dir} is not a statics outputs dir (needs run_meta.json and metrics.json); "
            "run `gptnt statics <task> --throw --dataset-revision <ref>` first."
        )

    statics_metadata = StaticsRunMetadata.model_validate_json(meta_path.read_text())

    bundle_name = BundleName(
        player_name=statics_metadata.capabilities.player_name,
        target=f"{task}@{statics_metadata.dataset.revision_label}",
        fingerprint=statics_metadata.capabilities.fingerprint,
        run_date=statics_metadata.run_date,
    )

    manifest = StaticsSubmission(
        submission_id=bundle_name.submission_id,
        # Leave blank to be filled in manually.
        submitter=Submitter(),
        players=[create_submission_player_entry("defuser", statics_metadata.capabilities)],
        dataset=statics_metadata.dataset,
        provenance=statics_metadata.provenance,
        run_date=bundle_name.run_date,
    )

    return write_bundle(
        into,
        bundle_name,
        manifest,
        lambda bundle_dir: (bundle_dir / "metrics.json").write_text(metrics_path.read_text()),
    )
