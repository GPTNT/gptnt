"""The deterministic checks behind `submission validate`.

Every check reads only the bundle (and, for the suite digest, the installed configs). None touches
the game, redis, or a model key. Each returns one `CheckResult`; a `fail` fails the command.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gptnt.cli.doctor.checks import CheckResult
from gptnt.cli.submission._io import load_suite
from gptnt.cli.submission._schema import compute_interactive_stats
from gptnt.experiments.models import ExperimentOutcome
from gptnt.specification import PlayerCapabilities

if TYPE_CHECKING:
    from gptnt.cli.submission._schema import (
        InteractiveSubmission,
        Provenance,
        SubmissionExperiment,
    )

_FLOAT_TOLERANCE = 1e-9


def _deep_equal(left: Any, right: Any) -> bool:
    """Structural equality that treats floats within `_FLOAT_TOLERANCE` as equal."""
    if isinstance(left, float) or isinstance(right, float):
        return (
            isinstance(left, (int, float))
            and isinstance(right, (int, float))
            and (abs(left - right) <= _FLOAT_TOLERANCE)
        )
    if isinstance(left, dict) and isinstance(right, dict):
        if left.keys() != right.keys():
            return False
        return all(_deep_equal(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(map(_deep_equal, left, right))
    return left == right


def check_stats_recompute(
    experiments: list[SubmissionExperiment], declared_stats: dict[str, Any]
) -> CheckResult:
    """The stats recomputed from `experiments.parquet` must match the manifest snapshot."""
    recomputed = compute_interactive_stats(experiments)
    if _deep_equal(recomputed, declared_stats):
        return CheckResult("stats", "pass", "headline and balances match experiments.parquet")
    return CheckResult(
        "stats",
        "fail",
        "declared stats do not match the recompute from experiments.parquet",
        "regenerate the bundle with `gptnt submission new`.",
    )


def check_outcomes(experiments: list[SubmissionExperiment]) -> CheckResult:
    """Each row's outcome flags must re-derive from its own final bomb state."""
    for experiment in experiments:
        derived = ExperimentOutcome.from_bomb_state(
            experiment.final_bomb_state, is_hard_crash=experiment.is_hard_crash
        )
        stored = ExperimentOutcome(
            is_solved=experiment.is_solved,
            is_detonated=experiment.is_detonated,
            is_timed_out=experiment.is_timed_out,
            is_strike_out=experiment.is_strike_out,
            is_hard_crash=experiment.is_hard_crash,
            seconds_remaining=experiment.seconds_remaining,
            strike_count=experiment.strike_count,
            num_modules_solved=experiment.num_modules_solved,
        )
        if derived != stored:
            return CheckResult(
                "outcomes",
                "fail",
                f"outcome for {experiment.attempt_name} does not match its final bomb state",
                "the row was edited away from its recorded bomb state.",
            )
    return CheckResult(
        "outcomes", "pass", f"{len(experiments)} outcomes re-derive from their bomb states"
    )


def check_suite_digest(manifest: InteractiveSubmission) -> CheckResult:
    """The suite digest must match the frozen suite at the installed code revision."""
    suite = load_suite(manifest.suite.suite_name)
    if suite.revision != manifest.suite.suite_revision:
        return CheckResult(
            "suite",
            "fail",
            f"declared revision {manifest.suite.suite_revision} != config revision {suite.revision}",
            "build against the code revision the results were produced at.",
        )
    if suite.suite_digest != manifest.suite.suite_digest:
        return CheckResult(
            "suite",
            "fail",
            "declared suite_digest does not match the frozen suite",
            "the suite config or its missions changed; rebuild at the pinned git_sha.",
        )
    return CheckResult(
        "suite",
        "pass",
        f"{manifest.suite.suite_name}@{manifest.suite.suite_revision} digest matches",
    )


def _fingerprint_matches(side: dict[str, Any]) -> bool:
    """A capability block reconstructs to a model whose fingerprint equals the stated one."""
    stated = side.get("fingerprint")
    capabilities = {key: setting for key, setting in side.items() if key != "fingerprint"}
    return PlayerCapabilities.model_validate(capabilities).fingerprint == stated


def _identity_failure(
    manifest: InteractiveSubmission, experiments: list[SubmissionExperiment]
) -> str | None:
    """The first inconsistency between the declared identity and the records, or None if clean."""
    defuser = manifest.capabilities["defuser"]
    expert = manifest.capabilities.get("expert")
    problems = [
        (
            manifest.system.model != defuser["player_name"],
            "system.model does not match player_name",
        ),
        (not _fingerprint_matches(defuser), "defuser capability fingerprint is inconsistent"),
        (
            any(
                exp.defuser_capability_fingerprint != defuser["fingerprint"] for exp in experiments
            ),
            "a row's defuser fingerprint differs from the manifest",
        ),
        (
            expert is not None and not _fingerprint_matches(expert),
            "expert fingerprint is inconsistent",
        ),
    ]
    return next((message for failed, message in problems if failed), None)


def check_identity(
    manifest: InteractiveSubmission, experiments: list[SubmissionExperiment]
) -> CheckResult:
    """Model name and per-side fingerprints must agree across the manifest and every row."""
    failure = _identity_failure(manifest, experiments)
    if failure is not None:
        return CheckResult("identity", "fail", failure)
    if not manifest.system.provider or not manifest.system.organization:
        return CheckResult(
            "identity",
            "warn",
            "provider/organization not declared",
            "fill in system.provider and system.organization in submission.yaml.",
        )
    return CheckResult(
        "identity", "pass", f"model {manifest.system.model!r} and fingerprints agree"
    )


def check_provenance(provenance: Provenance) -> CheckResult:
    """The git_sha must be a clean, recorded commit (a dirty tree is not installable there)."""
    sha = provenance.git_sha
    if sha is None:
        return CheckResult(
            "provenance", "fail", "no git_sha recorded", "results must be traceable to a commit."
        )
    if sha.endswith("-dirty"):
        return CheckResult(
            "provenance",
            "fail",
            "git_sha is from a dirty tree",
            "re-run the experiments from a committed, pushed tree.",
        )
    return CheckResult("provenance", "pass", f"clean git_sha {sha[:12]}")


def check_coverage(
    manifest: InteractiveSubmission, experiments: list[SubmissionExperiment]
) -> CheckResult:
    """Every row belongs to the declared suite, and no hard-crash is counted as valid."""
    if not experiments:
        return CheckResult("coverage", "fail", "no experiments in the bundle")

    suite = manifest.suite
    off_suite = [
        experiment.attempt_name
        for experiment in experiments
        if (experiment.suite_name, experiment.suite_revision)
        != (suite.suite_name, suite.suite_revision)
    ]
    if off_suite:
        return CheckResult(
            "coverage",
            "fail",
            f"{len(off_suite)} row(s) are not from {suite.suite_name}@{suite.suite_revision}",
        )
    if any(experiment.is_hard_crash and experiment.is_valid for experiment in experiments):
        return CheckResult("coverage", "fail", "a hard-crash experiment is counted as valid")

    valid = sum(1 for experiment in experiments if experiment.is_valid)
    return CheckResult("coverage", "pass", f"{len(experiments)} experiments, {valid} valid")


def interactive_checks(
    manifest: InteractiveSubmission, experiments: list[SubmissionExperiment]
) -> list[CheckResult]:
    """Run every interactive check and return the findings in report order."""
    return [
        check_stats_recompute(experiments, manifest.stats),
        check_outcomes(experiments),
        check_suite_digest(manifest),
        check_identity(manifest, experiments),
        check_provenance(manifest.provenance),
        check_coverage(manifest, experiments),
    ]
