"""The individual `gptnt submission validate` checks.

`load_bundle` parses a directory into a `LoadedBundle` or returns findings explaining why it
could not. The checks are methods on the loaded bundle, each returning :class:`CheckResult`s and
never raising. The manifest schema performs cheap gatekeeping itself. Unknown schema versions,
tampered fingerprints, blank identities, and kind discrimination all fail the parse. The methods
here
only cover what needs the directory, the payload, or the checkout: naming, coverage, and hygiene.
The command layer (`validate.py`) decides section order and rendering, reusing the shared
`CheckResult` and the `gptnt.cli.checks` render/format machinery.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import orjson
import yaml
from pydantic import ValidationError
from tomlkit.exceptions import TOMLKitError

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
    UnsupportedSubmissionSchemaError,
    describe_pairing,
)
from gptnt.experiments.db.typed_parquet import read_typed_parquet
from gptnt.experiments.suite.lock import SuiteLock, SuiteNotFrozenError
from gptnt.provenance import Provenance

if TYPE_CHECKING:
    from gptnt.experiments.suite.definition import Suite
    from gptnt.experiments.suite.lock import SuiteLockEntry
    from gptnt.ktane.mission_spec import KtaneMissionSpec
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
        """Return the one hand-filled block is actually filled in."""
        submitter = self.manifest.submitter
        fields = (("name", submitter.name), ("contact", submitter.contact))
        blank = [field_name for field_name, field_value in fields if not field_value.strip()]
        if blank:
            hint = "Fill in the `submitter` block in submission.yaml."
            return [CheckResult.failed("submitter", f"blank: {', '.join(blank)}", hint=hint)]
        return [CheckResult.passed("submitter", f"{submitter.name} ({submitter.contact})")]

    def check_provenance(self) -> list[CheckResult]:
        provenance = self.manifest.provenance
        findings = [
            _check_release_version(provenance.gptnt_version, provenance.release_tag),
            _check_release_commit(provenance.release_commit),
            _check_protected_content(modified=provenance.protected_content_modified),
        ]
        if isinstance(self.bundle, InteractiveBundle):
            manifest_provenance = provenance.model_dump()
            mismatched_rows = [
                index
                for index, experiment in enumerate(self.bundle.experiments)
                if experiment.model_dump(include=set(Provenance.model_fields))
                != manifest_provenance
            ]
            if mismatched_rows:
                findings.append(
                    CheckResult.failed(
                        "provenance",
                        f"payload rows {mismatched_rows} do not match submission.yaml",
                        hint=REBUILD_HINT,
                    )
                )
        else:
            findings.append(_check_dataset_pin(self.bundle.manifest.measured))
        return findings

    @property
    def _actual_dir(self) -> Path:
        """The flat `YYYYMMDD_<display>_<fp8>_<suite>_<ver>` folder this bundle is written to."""
        return Path(self.bundle_dir.name)

    def _check_stray_payload(self) -> CheckResult | None:
        """Return the other kind's payload file must not be lying around in this bundle."""
        other = StaticsBundle if isinstance(self.bundle, InteractiveBundle) else InteractiveBundle
        if not (self.bundle_dir / other.payload_filename).exists():
            return None
        detail = f"{other.payload_filename} does not belong in this bundle"
        return CheckResult.failed("layout", detail, hint=REBUILD_HINT)

    def _check_directory_name(self) -> CheckResult | None:
        """Return the directory must be exactly what `BundleName` derives from the manifest."""
        expected = BundleName.from_manifest(self.manifest).relative_dir
        if expected == self._actual_dir:
            return None
        detail = f"expected …/{expected}, found …/{self._actual_dir}"
        return CheckResult.failed("directory", detail, hint=REBUILD_HINT)

    def _check_submission_id(self) -> CheckResult | None:
        """Return the stored id must be exactly what `BundleName` derives from the manifest."""
        expected = BundleName.from_manifest(self.manifest).submission_id
        if expected == self.manifest.submission_id:
            return None
        detail = f"expected {expected}, manifest says {self.manifest.submission_id}"
        return CheckResult.failed("submission_id", detail, hint=REBUILD_HINT)


def check_suite(bundle: InteractiveBundle) -> list[CheckResult]:
    """Return the bundled lock contains one matching entry and exactly its missions."""
    if len(bundle.suite_lock.suites) != 1:
        return [
            CheckResult.failed(
                "suite snapshot",
                f"expected one suite entry, found {len(bundle.suite_lock.suites)}",
                hint=REBUILD_HINT,
            )
        ]
    entry = bundle.suite_lock.suites[0]
    declared = bundle.manifest.measured
    findings = []
    if (declared.suite_name, declared.suite_revision) == (entry.name, entry.revision):
        findings.append(CheckResult.passed("suite", declared.target))
    else:
        findings.append(
            CheckResult.failed(
                "suite",
                f"snapshot has {entry.name}@{entry.revision}, manifest says {declared.target}",
                hint=REBUILD_HINT,
            )
        )
    findings.append(_check_suite_digest(declared.suite_digest, entry.suite_digest))

    referenced = set(entry.mission_digests)
    stored = set(bundle.suite_lock.mission_specs().keys())
    if referenced == stored:
        findings.append(
            CheckResult.passed("snapshot missions", f"exactly {len(referenced)} missions")
        )
    else:
        parts = []
        if missing := sorted(referenced - stored):
            parts.append(f"missing: {', '.join(missing)}")
        if extra := sorted(stored - referenced):
            parts.append(f"extra: {', '.join(extra)}")
        findings.append(
            CheckResult.failed("snapshot missions", "; ".join(parts), hint=REBUILD_HINT)
        )
    return findings


def check_installed_lock_match(
    bundle: InteractiveBundle, installed_suite_registry: SuiteLock
) -> CheckResult:
    """Require the bundle snapshot to equal this installation's suite-registry snapshot."""
    entry = bundle.suite_lock.suites[0]
    try:
        installed_snapshot = installed_suite_registry.snapshot(entry.name, entry.revision)
    except SuiteNotFrozenError:
        return CheckResult.failed(
            "installed suite registry",
            f"{entry.name}@{entry.revision} is absent from the installed suite registry",
            hint=REBUILD_HINT,
        )
    if bundle.suite_lock != installed_snapshot:
        return CheckResult.failed(
            "installed suite registry",
            f"{entry.name}@{entry.revision} does not exactly match the installed suite registry",
            hint=REBUILD_HINT,
        )
    return CheckResult.passed("installed suite registry", f"{entry.name}@{entry.revision}")


def check_mission_coverage(bundle: InteractiveBundle, entry: SuiteLockEntry) -> list[CheckResult]:
    """Return every (expert, mission) pairing the manifest declares has exactly one, valid run."""
    manifest = bundle.manifest
    experiments = bundle.experiments
    defuser = manifest.player.capabilities
    # A submission fixes one defuser. Solo play has no expert (an empty fingerprint marker).
    experts = [player.capabilities for player in manifest.players[1:]] or [None]
    expected = {
        (defuser.fingerprint, expert.fingerprint if expert else "", mission_key): describe_pairing(
            defuser.player_name, expert.player_name if expert else None, mission_key
        )
        for expert in experts
        for mission_key in bundle.suite_lock.mission_keys_for(entry)
    }
    return [
        _check_experiments_belong_to_suite(bundle, entry),
        *_check_one_run_per_mission_per_pairing(expected, experiments),
        _check_experiment_outcomes(experiments),
    ]


def check_players(bundle: InteractiveBundle) -> list[CheckResult]:
    """Return the payload was played by exactly the players the manifest declares.

    This is bundle-internal. Nothing here reads `configs/player/`. The manifest's own shape,
    including identities, fingerprints, and the one-defuser-first order, is schema-enforced.
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
    bundle, payload_findings = _load_payload(bundle_dir, manifest)
    findings = [manifest_finding, *payload_findings]
    if bundle is None:
        return None, findings
    return LoadedBundle(bundle_dir=bundle_dir, bundle=bundle), findings


def _check_protected_content(*, modified: bool | None) -> CheckResult:
    """Reject records produced while protected benchmark content differed from the release."""
    if modified is None:
        return CheckResult.failed(
            "protected content",
            "not assessed because the run has no release provenance",
            "Run the benchmark from an unmodified release checkout, then rebuild the submission.",
        )
    if modified:
        return CheckResult.failed(
            "protected content",
            "recorded as modified from the release",
            "Run the benchmark from an unmodified release checkout, then rebuild the submission.",
        )
    return CheckResult.passed("protected content", "matches")


def _invalid_manifest_finding(
    error: yaml.YAMLError | ValidationError | ValueError | TypeError,
) -> CheckResult:
    """Classify project-owned manifest identities before reporting other schema failures."""
    if isinstance(error, ValidationError):
        fingerprint_error = next(
            (
                detail["msg"]
                for detail in error.errors(include_url=False)
                if "serialised fingerprint" in detail["msg"]
            ),
            None,
        )
        if fingerprint_error is not None:
            return CheckResult.failed("player fingerprint", fingerprint_error, hint=REBUILD_HINT)
    return CheckResult.failed("manifest", f"submission.yaml is not a valid manifest: {error}")


def _load_manifest(
    bundle_dir: Path,
) -> tuple[InteractiveSubmission | StaticsSubmission | None, CheckResult]:
    """Parse `submission.yaml`, turning every way it can be broken into one finding."""
    try:
        manifest = load_submission_manifest(bundle_dir)
    except FileNotFoundError:
        return None, CheckResult.failed("manifest", "submission.yaml not found", hint=REBUILD_HINT)
    except UnsupportedSubmissionSchemaError as error:
        return None, CheckResult.failed("schema_version", str(error))
    except _MANIFEST_ERRORS as error:
        return None, _invalid_manifest_finding(error)
    kind = "interactive" if isinstance(manifest, InteractiveSubmission) else "statics"
    return manifest, CheckResult.passed("manifest", f"{kind} manifest")


def _load_payload(
    bundle_dir: Path, manifest: InteractiveSubmission | StaticsSubmission
) -> tuple[InteractiveBundle | StaticsBundle | None, list[CheckResult]]:
    """Read the payload file the manifest's kind demands, into a full bundle."""
    if isinstance(manifest, StaticsSubmission):
        return _load_statics_payload(bundle_dir, manifest)
    return _load_interactive_payload(bundle_dir, manifest)


def _load_statics_payload(
    bundle_dir: Path, manifest: StaticsSubmission
) -> tuple[StaticsBundle | None, list[CheckResult]]:
    payload_path = bundle_dir / StaticsBundle.payload_filename
    if not payload_path.exists():
        return None, [CheckResult.failed("payload", "metrics.json not found", hint=REBUILD_HINT)]
    metrics_text = payload_path.read_text()
    try:
        orjson.loads(metrics_text)
    except orjson.JSONDecodeError as error:
        return None, [CheckResult.failed("payload", f"metrics.json is not valid JSON: {error}")]
    bundle = StaticsBundle(manifest=manifest, metrics_text=metrics_text)
    return bundle, [CheckResult.passed("payload", "metrics.json")]


def _load_interactive_payload(
    bundle_dir: Path, manifest: InteractiveSubmission
) -> tuple[InteractiveBundle | None, list[CheckResult]]:
    payload_path = bundle_dir / InteractiveBundle.payload_filename
    if not payload_path.exists():
        return None, [
            CheckResult.failed("payload", "experiments.parquet not found", hint=REBUILD_HINT)
        ]
    try:
        experiments = read_typed_parquet(SubmissionExperiment, payload_path)
    except Exception as error:  # noqa: BLE001  (pyarrow/pydantic raise many kinds; all mean a broken payload)
        return None, [
            CheckResult.failed("payload", f"experiments.parquet did not read back: {error}")
        ]
    if not experiments:
        return None, [CheckResult.failed("payload", "experiments.parquet is empty")]

    payload_finding = CheckResult.passed(
        "payload", f"experiments.parquet ({len(experiments)} experiments)"
    )
    snapshot, snapshot_finding = _load_suite_snapshot(bundle_dir)
    if snapshot is None:
        return None, [payload_finding, snapshot_finding]
    bundle = InteractiveBundle(manifest=manifest, experiments=experiments, suite_lock=snapshot)
    return bundle, [payload_finding, snapshot_finding]


def _load_suite_snapshot(bundle_dir: Path) -> tuple[SuiteLock | None, CheckResult]:
    """Read the bundled `suite.lock` and classify malformed snapshot content."""
    snapshot_path = bundle_dir / InteractiveBundle.snapshot_filename
    if not snapshot_path.exists():
        return None, CheckResult.failed(
            "suite snapshot", "suite.lock not found", hint=REBUILD_HINT
        )
    try:
        snapshot = SuiteLock.from_lock_path(snapshot_path)
    except (SuiteNotFrozenError, TOMLKitError, ValidationError) as error:
        return None, _invalid_snapshot_finding(error)
    except ValueError as error:
        return None, _invalid_snapshot_finding(error)
    return snapshot, CheckResult.passed("suite snapshot", "suite.lock")


def _invalid_snapshot_finding(error: Exception) -> CheckResult:
    """Classify a lock-read failure for concise submission-validation output."""
    detail = str(error)
    if "digest does not match" in detail:
        name = "snapshot digest"
    elif "mission digests absent from the table" in detail:
        name = "snapshot missions"
    else:
        name = "suite snapshot"
    return CheckResult.failed(name, f"suite.lock is not valid: {detail}")


def _check_suite_digest(declared_digest: str, frozen_digest: str) -> CheckResult:
    """Check the bundle's claimed digest against the frozen digest for this revision."""
    if frozen_digest != declared_digest:
        return CheckResult.failed(
            "suite digest",
            f"lock has {frozen_digest}, manifest says {declared_digest}",
            hint=REBUILD_HINT,
        )
    return CheckResult.passed("suite digest", frozen_digest)


def _check_experiments_belong_to_suite(
    bundle: InteractiveBundle, entry: SuiteLockEntry
) -> CheckResult:
    """Return every experiment must match the manifest identity and frozen suite content."""
    declared = bundle.manifest.measured
    suite, missions = bundle.suite_lock.load_suite(entry.name, entry.revision)
    mission_specs = {mission.mission_key: mission for mission in missions}
    suite_key = (
        declared.suite_name,
        declared.suite_revision,
        declared.suite_digest,
        entry.mission_set,
    )
    mismatched = [
        index
        for index, experiment in enumerate(bundle.experiments)
        if not _experiment_matches_snapshot(
            experiment, suite_key=suite_key, mission_specs=mission_specs, suite=suite
        )
    ]
    if mismatched:
        detail = f"payload rows {mismatched} do not match {declared.target} and its snapshot"
        return CheckResult.failed("experiments", detail)
    return CheckResult.passed(
        "experiments", f"all {len(bundle.experiments)} experiments match {declared.target}"
    )


def _experiment_matches_snapshot(
    experiment: SubmissionExperiment,
    *,
    suite_key: tuple[str, int, str, str],
    mission_specs: dict[str, KtaneMissionSpec],
    suite: Suite,
) -> bool:
    """Return whether one payload row matches every frozen suite field it records."""
    identity_matches = (
        experiment.suite_name,
        experiment.suite_revision,
        experiment.suite_digest,
        experiment.mission_set,
    ) == suite_key
    content_matches = (
        experiment.mission_spec == mission_specs.get(experiment.mission_key)
        and experiment.manual_profile == suite.manual_profile
        and experiment.defuser_protocol == suite.defuser_protocol
        and experiment.expert_protocol == suite.expert_protocol
    )
    return identity_matches and content_matches


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
    """Return every experiment must have been played by the manifest's defuser capability."""
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
    """Return the manifest's expert entries and the payload's experts must be the same set."""
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


def _check_release_version(version: str, release_tag: str | None) -> CheckResult:
    """Require the package version to identify the recorded release tag."""
    if release_tag is None:
        return CheckResult.failed(
            "gptnt_version", f"gptnt_version {version!r} has no release_tag", hint=REBUILD_HINT
        )
    expected = release_tag.removeprefix("v")
    if version != expected:
        return CheckResult.failed(
            "gptnt_version",
            f"gptnt_version {version!r} does not match release_tag {release_tag!r}",
            hint=REBUILD_HINT,
        )
    return CheckResult.passed("gptnt_version", f"{release_tag} ({version})")


def _check_release_commit(release_commit: str | None) -> CheckResult:
    """Require the complete lowercase Git SHA-1 written by the release checkout."""
    if release_commit is not None and re.fullmatch(r"[0-9a-f]{40}", release_commit):
        return CheckResult.passed("release_commit", release_commit)
    return CheckResult.failed(
        "release_commit", f"{release_commit!r} is not a complete commit SHA", hint=REBUILD_HINT
    )


def _check_dataset_pin(statics: StaticsIdentity) -> CheckResult:
    if not statics.is_pinned:
        return CheckResult.warned(
            "dataset pin",
            f"{statics.hf_repo_id} has no pinned revision",
            hint="Re-run with `--dataset-revision <ref>` for a reproducible submission.",
        )
    return CheckResult.passed("dataset pin", f"{statics.hf_repo_id}@{statics.revision_label}")
