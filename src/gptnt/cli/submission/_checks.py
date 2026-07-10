"""The individual `gptnt submission validate` checks.

`load_bundle` parses a directory into a `LoadedBundle` — or the findings explaining why it
couldn't — and the checks are methods on it, each returning :class:`CheckResult`s and never
raising. The manifest schema does the cheap gatekeeping itself (unknown schema versions, tampered
fingerprints, blank identities, and kind discrimination all fail the parse), so the methods here
only cover what needs the directory, the payload, or the checkout: naming, coverage, and hygiene.
The command layer (`validate.py`) decides section order and rendering, reusing the shared
`CheckResult` and the `gptnt.cli.checks` render/format machinery.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import ValidationError

from gptnt.cli.checks.result import CheckResult
from gptnt.cli.submission._bundle import (
    BundleName,
    InteractiveBundle,
    StaticsBundle,
    load_submission_manifest,
)
from gptnt.cli.submission._schema import (
    InteractiveSubmission,
    StaticsSubmission,
    SubmissionExperiment,
    SubmissionPairingKey,
    describe_pairing,
)
from gptnt.experiments.db.typed_parquet import read_typed_parquet
from gptnt.experiments.provenance import is_dirty_sha, is_valid_version

if TYPE_CHECKING:
    from gptnt.experiments.suite.lock import SuiteLockEntry
    from gptnt.statics.run_metadata import StaticsIdentity

REBUILD_HINT = "Rebuild with `gptnt submission new`."

# Everything a malformed submission.yaml can raise on the way through yaml + pydantic parsing.
_MANIFEST_ERRORS = (yaml.YAMLError, ValidationError, ValueError, TypeError)


@dataclass(frozen=True)
class LoadedBundle:
    """One bundle directory paired with its parsed contents, ready for the content checks."""

    bundle_dir: Path
    bundle: InteractiveBundle | StaticsBundle

    @property
    def manifest(self) -> InteractiveSubmission | StaticsSubmission:
        return self.bundle.manifest

    def check_structure(self) -> list[CheckResult]:
        """No stray payload, and the directory matches the manifest-derived naming."""
        problems = (
            self._check_stray_payload(),
            self._check_directory_name(),
            self._check_submission_id(),
        )
        findings = [finding for finding in problems if finding is not None]
        return findings or [CheckResult.passed("naming", detail=str(self._actual_dir))]

    def check_submitter(self) -> list[CheckResult]:
        """The one hand-filled block is actually filled in."""
        submitter = self.manifest.submitter
        fields = (("name", submitter.name), ("contact", submitter.contact))
        blank = [field_name for field_name, field_value in fields if not field_value.strip()]
        if blank:
            hint = "Fill in the `submitter` block in submission.yaml."
            return [CheckResult.failed("submitter", f"blank: {', '.join(blank)}", hint=hint)]
        return [CheckResult.passed("submitter", f"{submitter.name} ({submitter.contact})")]

    def check_provenance(self) -> list[CheckResult]:
        """Provenance is present; hygiene issues (dirty tree, unpinned dataset) only warn."""
        provenance = self.manifest.provenance
        findings = [
            _check_gptnt_version(provenance.gptnt_version),
            _check_git_sha(provenance.git_sha),
        ]
        if isinstance(self.bundle, StaticsBundle):
            findings.append(_check_dataset_pin(self.bundle.manifest.measured))
        return findings

    @property
    def _actual_dir(self) -> Path:
        """The flat `YYYYMMDD_<display>_<fp8>_<suite>_<ver>` folder this bundle lives at."""
        return Path(self.bundle_dir.name)

    def _check_stray_payload(self) -> CheckResult | None:
        """The other kind's payload file must not be lying around in this bundle."""
        other = StaticsBundle if isinstance(self.bundle, InteractiveBundle) else InteractiveBundle
        if not (self.bundle_dir / other.payload_filename).exists():
            return None
        detail = f"{other.payload_filename} does not belong in this bundle"
        return CheckResult.failed("layout", detail, hint=REBUILD_HINT)

    def _check_directory_name(self) -> CheckResult | None:
        """The directory must be exactly what `BundleName` derives from the manifest."""
        expected = BundleName.from_manifest(self.manifest).relative_dir
        if expected == self._actual_dir:
            return None
        detail = f"expected …/{expected}, found …/{self._actual_dir}"
        return CheckResult.failed("directory", detail, hint=REBUILD_HINT)

    def _check_submission_id(self) -> CheckResult | None:
        """The stored id must be exactly what `BundleName` derives from the manifest."""
        expected = BundleName.from_manifest(self.manifest).submission_id
        if expected == self.manifest.submission_id:
            return None
        detail = f"expected {expected}, manifest says {self.manifest.submission_id}"
        return CheckResult.failed("submission_id", detail, hint=REBUILD_HINT)


def check_suite(
    bundle: InteractiveBundle, entry: SuiteLockEntry | None, *, lookup_error: str = ""
) -> list[CheckResult]:
    """The declared suite revision is frozen in the lock and unchanged since the bundle built."""
    if entry is None:
        return [CheckResult.failed("suite", lookup_error)]
    declared = bundle.manifest.measured
    return [
        CheckResult.passed("suite", f"{entry.name}@{entry.revision}"),
        _check_suite_digest(declared.suite_digest, entry.suite_digest),
    ]


def check_mission_coverage(bundle: InteractiveBundle, entry: SuiteLockEntry) -> list[CheckResult]:
    """Every (expert, mission) pairing the manifest declares has exactly one, valid run."""
    manifest = bundle.manifest
    experiments = bundle.experiments
    defuser = manifest.player.capabilities
    # A submission fixes one defuser; solo play has no expert (an empty fingerprint marker).
    experts = [player.capabilities for player in manifest.players[1:]] or [None]
    expected = {
        (defuser.fingerprint, expert.fingerprint if expert else "", mission_key): describe_pairing(
            defuser.player_name, expert.player_name if expert else None, mission_key
        )
        for expert in experts
        for mission_key in entry.mission_keys
    }
    return [
        _check_experiments_belong_to_suite(entry, experiments),
        *_check_one_run_per_mission_per_pairing(expected, experiments),
        _check_experiment_outcomes(experiments),
    ]


def check_players(bundle: InteractiveBundle) -> list[CheckResult]:
    """The payload was played by exactly the players the manifest declares.

    Deliberately bundle-internal (nothing here reads configs/player/); the manifest's own shape —
    identities, fingerprints, one-defuser-first — is already schema-enforced.
    """
    manifest = bundle.manifest
    experiments = bundle.experiments
    return [
        _check_defuser_matches_manifest(manifest, experiments),
        _check_experts_match_manifest(manifest, experiments),
    ]


def load_bundle(bundle_dir: Path) -> tuple[LoadedBundle | None, list[CheckResult]]:
    """Parse a bundle dir into a `LoadedBundle`, or the findings explaining why it can't be."""
    manifest, manifest_finding = _load_manifest(bundle_dir)
    if manifest is None:
        return None, [manifest_finding]
    bundle, payload_finding = _load_payload(bundle_dir, manifest)
    findings = [manifest_finding, payload_finding]
    if bundle is None:
        return None, findings
    return LoadedBundle(bundle_dir=bundle_dir, bundle=bundle), findings


def _load_manifest(
    bundle_dir: Path,
) -> tuple[InteractiveSubmission | StaticsSubmission | None, CheckResult]:
    """Parse `submission.yaml`, turning every way it can be broken into one finding."""
    try:
        manifest = load_submission_manifest(bundle_dir)
    except FileNotFoundError:
        return None, CheckResult.failed("manifest", "submission.yaml not found", hint=REBUILD_HINT)
    except _MANIFEST_ERRORS as error:
        return None, CheckResult.failed(
            "manifest", f"submission.yaml is not a valid manifest: {error}"
        )
    kind = "interactive" if isinstance(manifest, InteractiveSubmission) else "statics"
    return manifest, CheckResult.passed("manifest", f"{kind} manifest")


def _load_payload(
    bundle_dir: Path, manifest: InteractiveSubmission | StaticsSubmission
) -> tuple[InteractiveBundle | StaticsBundle | None, CheckResult]:
    """Read the payload file the manifest's kind demands, into a full bundle."""
    if isinstance(manifest, StaticsSubmission):
        return _load_statics_payload(bundle_dir, manifest)
    return _load_interactive_payload(bundle_dir, manifest)


def _load_statics_payload(
    bundle_dir: Path, manifest: StaticsSubmission
) -> tuple[StaticsBundle | None, CheckResult]:
    payload_path = bundle_dir / StaticsBundle.payload_filename
    if not payload_path.exists():
        return None, CheckResult.failed("payload", "metrics.json not found", hint=REBUILD_HINT)
    metrics_text = payload_path.read_text()
    try:
        json.loads(metrics_text)
    except json.JSONDecodeError as error:
        return None, CheckResult.failed("payload", f"metrics.json is not valid JSON: {error}")
    bundle = StaticsBundle(manifest=manifest, metrics_text=metrics_text)
    return bundle, CheckResult.passed("payload", "metrics.json")


def _load_interactive_payload(
    bundle_dir: Path, manifest: InteractiveSubmission
) -> tuple[InteractiveBundle | None, CheckResult]:
    payload_path = bundle_dir / InteractiveBundle.payload_filename
    if not payload_path.exists():
        return None, CheckResult.failed(
            "payload", "experiments.parquet not found", hint=REBUILD_HINT
        )
    try:
        experiments = read_typed_parquet(SubmissionExperiment, payload_path)
    except Exception as error:  # noqa: BLE001 — pyarrow/pydantic raise many kinds; all mean a broken payload
        return None, CheckResult.failed(
            "payload", f"experiments.parquet did not read back: {error}"
        )
    if not experiments:
        return None, CheckResult.failed("payload", "experiments.parquet is empty")
    bundle = InteractiveBundle(manifest=manifest, experiments=experiments)
    return bundle, CheckResult.passed(
        "payload", f"experiments.parquet ({len(experiments)} experiments)"
    )


def _check_suite_digest(declared_digest: str, frozen_digest: str) -> CheckResult:
    """The bundle's claimed digest must equal the frozen digest for this revision in the lock."""
    if frozen_digest != declared_digest:
        return CheckResult.failed(
            "suite digest",
            f"lock has {frozen_digest}, manifest says {declared_digest}",
            hint=REBUILD_HINT,
        )
    return CheckResult.passed("suite digest", frozen_digest)


def _check_experiments_belong_to_suite(
    entry: SuiteLockEntry, experiments: list[SubmissionExperiment]
) -> CheckResult:
    """Every experiment must have been recorded against this suite (and its mission set)."""
    suite_key = (entry.name, entry.revision, entry.mission_set)
    strays = sorted(
        {
            experiment.mission_key
            for experiment in experiments
            if (experiment.suite_name, experiment.suite_revision, experiment.mission_set)
            != suite_key
        }
    )
    if strays:
        detail = f"{len(strays)} experiment(s) not from {entry.name}@{entry.revision}: {', '.join(strays)}"
        return CheckResult.failed("experiments", detail)
    return CheckResult.passed(
        "experiments", f"all {len(experiments)} experiments from {entry.name}@{entry.revision}"
    )


def _check_one_run_per_mission_per_pairing(
    expected: dict[SubmissionPairingKey, str], experiments: list[SubmissionExperiment]
) -> list[CheckResult]:
    """Exactly one run per mission per pairing, reported as missing / duplicates / unknown.

    The identity is the (defuser, expert, mission) triple: a pairwise suite plays each mission
    once per expert, so counting on the mission alone would flag those legitimate pairings as
    duplicates. `expected` maps each pairing to its readable label; present runs describe
    themselves.
    """
    actual = Counter(experiment.pairing_key for experiment in experiments)
    described = expected | {exp.pairing_key: exp.pairing_description for exp in experiments}
    missing = sorted(described[key] for key in expected.keys() - actual.keys())
    duplicates = sorted(described[key] for key, count in actual.items() if count > 1)
    unknown = sorted(described[key] for key in actual.keys() - expected.keys())

    findings = []
    if missing:
        detail = f"{len(missing)}/{len(expected)} missions have no run: {', '.join(missing)}"
        findings.append(CheckResult.failed("missing", detail))
    if duplicates:
        findings.append(
            CheckResult.failed(
                "duplicates",
                f"more than one run for: {', '.join(duplicates)}",
                hint="Each mission gets exactly one run; drop the retries before submitting.",
            )
        )
    if unknown:
        findings.append(
            CheckResult.failed(
                "unknown", f"runs of missions not in the suite: {', '.join(unknown)}"
            )
        )
    if not findings:
        findings.append(
            CheckResult.passed("coverage", f"all {len(expected)} missions covered exactly once")
        )
    return findings


def _check_experiment_outcomes(experiments: list[SubmissionExperiment]) -> CheckResult:
    """Each bundled run must have ended cleanly (the shared `is_valid_outcome` definition)."""
    invalid = sorted(
        experiment.mission_key for experiment in experiments if not experiment.is_valid
    )
    if invalid:
        return CheckResult.failed(
            "outcomes",
            f"{len(invalid)} run(s) did not end cleanly: {', '.join(invalid)}",
            hint="Crashed or unfinished runs can't be submitted; re-run these missions.",
        )
    return CheckResult.passed("outcomes", "every run ended cleanly")


def _check_defuser_matches_manifest(
    manifest: InteractiveSubmission, experiments: list[SubmissionExperiment]
) -> CheckResult:
    """Every experiment must have been played by the manifest's defuser capability."""
    defuser_fingerprint = manifest.player.capabilities.fingerprint
    mismatched = sum(
        experiment.defuser_capability_fingerprint != defuser_fingerprint
        for experiment in experiments
    )
    if mismatched:
        detail = f"{mismatched} experiment(s) ran a different defuser capability than the manifest"
        return CheckResult.failed("defuser", detail, hint=REBUILD_HINT)
    return CheckResult.passed("defuser", "every experiment matches the manifest defuser")


def _check_experts_match_manifest(
    manifest: InteractiveSubmission, experiments: list[SubmissionExperiment]
) -> CheckResult:
    """The manifest's expert entries and the payload's experts must be the same set."""
    manifest_experts = {player.capabilities.fingerprint for player in manifest.players[1:]}
    row_experts = {
        experiment.expert_capability_fingerprint
        for experiment in experiments
        if experiment.expert_capabilities is not None
    }
    if manifest_experts != row_experts:
        detail = (
            f"manifest experts {sorted(manifest_experts)} != payload experts {sorted(row_experts)}"
        )
        return CheckResult.failed("experts", detail, hint=REBUILD_HINT)
    detail = f"{len(manifest_experts)} expert(s) match" if manifest_experts else "solo play"
    return CheckResult.passed("experts", detail)


def _check_gptnt_version(version: str) -> CheckResult:
    if is_valid_version(version):
        return CheckResult.passed("gptnt_version", version)
    detail = f"{version!r} is not a valid version" if version.strip() else "missing"
    return CheckResult.failed("gptnt_version", detail, hint=REBUILD_HINT)


def _check_git_sha(git_sha: str | None) -> CheckResult:
    if git_sha is None:
        return CheckResult.warned("git_sha", "not recorded (git unavailable at run time)")
    if is_dirty_sha(git_sha):
        return CheckResult.warned(
            "git_sha", f"{git_sha} — the tree had uncommitted changes at run time"
        )
    return CheckResult.passed("git_sha", git_sha)


def _check_dataset_pin(statics: StaticsIdentity) -> CheckResult:
    if not statics.is_pinned:
        return CheckResult.warned(
            "dataset pin",
            f"{statics.hf_repo_id} has no pinned revision",
            hint="Re-run with `--dataset-revision <ref>` for a reproducible submission.",
        )
    return CheckResult.passed("dataset pin", f"{statics.hf_repo_id}@{statics.revision_label}")
