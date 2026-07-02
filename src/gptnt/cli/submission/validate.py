from pathlib import Path

from rich.console import Console

from gptnt.cli.doctor.render import render_report
from gptnt.cli.submission._checks import interactive_checks
from gptnt.cli.submission._io import read_experiments, read_yaml
from gptnt.cli.submission._schema import InteractiveSubmission
from gptnt.cli.submission._statics_checks import statics_checks

console = Console()


def validate_submission(bundle_dir: Path) -> None:
    """Check a submission bundle: deterministic internal consistency plus a score recompute.

    Runs every check without the game, redis, or model keys. Exits nonzero on any failure.
    """
    manifest_data = read_yaml(bundle_dir / "submission.yaml")

    if "suite" in manifest_data:
        manifest = InteractiveSubmission.model_validate(manifest_data)
        findings = interactive_checks(
            manifest, read_experiments(bundle_dir / "experiments.parquet")
        )
    elif "dataset" in manifest_data:
        findings = statics_checks(bundle_dir, manifest_data)
    else:
        raise RuntimeError(
            f"{bundle_dir / 'submission.yaml'} has neither a `suite` nor a `dataset` block."
        )

    render_report(console, {"Submission": findings})
    if any(finding.status == "fail" for finding in findings):
        raise RuntimeError("Submission validation failed; see the rows above.")
