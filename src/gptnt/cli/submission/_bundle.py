"""What a submission bundle is: its naming, its two shapes, and how each saves and loads.

A bundle is one directory per (model, target):

    <output>/<model-slug>_<capfp8>/<target>@<revision>/
        submission.yaml       # the manifest; every derived field regenerated on rebuild
        experiments.parquet   # interactive payload, or
        metrics.json          # statics payload

`InteractiveBundle` and `StaticsBundle` pair a manifest with its payload: built via a `from_*`
constructor, written with `save()` (which preserves a hand-filled `submitter` on rebuild), and
read back with `load_submission_bundle()`. The manifest is self-describing, so `BundleName` — the
single source of the `submission_id` and the directory — is derived from it alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Self, override

import yaml

from gptnt.cli.submission._schema import (
    InteractiveSubmission,
    StaticsSubmission,
    SubmissionExperiment,
    SubmissionPlayer,
    Submitter,
    parse_submission_manifest,
)
from gptnt.experiments.db.typed_parquet import read_typed_parquet, write_typed_parquet
from gptnt.experiments.provenance import ProvenanceMixin
from gptnt.experiments.suite import SuiteIdentity
from gptnt.statics.run_metadata import StaticsRunMetadata

if TYPE_CHECKING:
    from whenever import Instant

    from gptnt.experiments.suite import Suite
    from gptnt.players.specification import PlayerCapabilities

_SHORT_FINGERPRINT_LENGTH = 8


def slugify(name: str) -> str:
    """Lowercase, and collapse any run of non-`[a-z0-9]` into one dash (dots become dashes)."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@dataclass(frozen=True)
class BundleName:
    """The single source of a bundle's naming: who ran what, fingerprinted and dated."""

    player_name: str
    """Recorded `player_name` of the model being submitted (the defuser)."""

    target: str
    """What was measured, with its pin: `<suite>@<revision>` or `<task>@<revision>`."""

    fingerprint: str
    """The model's full capability fingerprint."""

    run_date: Instant
    """When the earliest included experiment started."""

    @classmethod
    def from_manifest(cls, manifest: InteractiveSubmission | StaticsSubmission) -> Self:
        """Rebuild the naming from a manifest alone (it is fully self-describing)."""
        capabilities = manifest.player.capabilities
        return cls(
            player_name=capabilities.player_name,
            target=manifest.target,
            fingerprint=capabilities.fingerprint,
            run_date=manifest.run_date,
        )

    @property
    def submission_id(self) -> str:
        """The manifest's unique id: date, model, target, and short capability fingerprint."""
        date_label = self.run_date.format_iso()[:10]
        return f"{date_label}_{slugify(self.player_name)}_{self._short_fingerprint}_{self.target}"

    @property
    def relative_dir(self) -> Path:
        """Where the bundle lives under the output dir: `<model-slug>_<cap-fp>/<target>/`."""
        return Path(f"{slugify(self.player_name)}_{self._short_fingerprint}") / self.target

    @property
    def _short_fingerprint(self) -> str:
        return self.fingerprint[:_SHORT_FINGERPRINT_LENGTH]


@dataclass(kw_only=True, frozen=True)
class SubmissionBundle[ManifestT: InteractiveSubmission | StaticsSubmission]:
    """A manifest paired with its payload; subclasses declare the payload and how to write it."""

    manifest: ManifestT

    payload_filename: ClassVar[str]

    def save(self, output_root: Path) -> Path:
        """Write the bundle dir under `output_root` (keeping any hand-filled submitter)."""
        bundle_dir = output_root / BundleName.from_manifest(self.manifest).relative_dir
        bundle_dir.mkdir(parents=True, exist_ok=True)
        self._write_payload(bundle_dir)
        _write_manifest(bundle_dir, self.manifest)
        return bundle_dir

    def _write_payload(self, bundle_dir: Path) -> None:
        raise NotImplementedError


@dataclass(kw_only=True, frozen=True)
class InteractiveBundle(SubmissionBundle[InteractiveSubmission]):
    """An interactive submission: the manifest plus its `experiments.parquet` payload."""

    experiments: list[SubmissionExperiment]

    payload_filename: ClassVar[str] = "experiments.parquet"

    @classmethod
    def from_experiments(
        cls,
        experiments: list[SubmissionExperiment],
        suite: Suite,
        submitter: Submitter | None = None,
    ) -> Self:
        """Bundle one model's experiments for one frozen suite."""
        canonical = experiments[0]
        measured = SuiteIdentity.from_suite(suite)
        run_date = min(experiment.experiment_descriptor.start_time for experiment in experiments)
        name = BundleName(
            player_name=canonical.defuser_capabilities.player_name,
            target=measured.target,
            fingerprint=canonical.defuser_capabilities.fingerprint,
            run_date=run_date,
        )
        manifest = InteractiveSubmission(
            submission_id=name.submission_id,
            measured=measured,
            submitter=submitter or Submitter(),
            players=[
                SubmissionPlayer.for_role("defuser", canonical.defuser_capabilities),
                *(
                    SubmissionPlayer.for_role("expert", capabilities)
                    for capabilities in _collect_distinct_experts(experiments)
                ),
            ],
            provenance=ProvenanceMixin(
                gptnt_version=canonical.gptnt_version, git_sha=canonical.git_sha
            ),
            run_date=run_date,
        )
        return cls(manifest=manifest, experiments=experiments)

    @override
    def _write_payload(self, bundle_dir: Path) -> None:
        write_typed_parquet(self.experiments, file_path=bundle_dir / self.payload_filename)


@dataclass(kw_only=True, frozen=True)
class StaticsBundle(SubmissionBundle[StaticsSubmission]):
    """A statics submission: the manifest plus its verbatim `metrics.json` text."""

    metrics_text: str

    payload_filename: ClassVar[str] = "metrics.json"

    @classmethod
    def from_run_dir(
        cls,
        statics_output_dir: Path,
        *,
        metadata: StaticsRunMetadata | None = None,
        submitter: Submitter | None = None,
    ) -> Self:
        """Bundle one statics run from its outputs dir (`submitter` stays blank for a human).

        The task is read off the stamped `run_meta.json`, not the directory name — the run's own
        metadata is the source of truth for what was measured. Pass `metadata` to reuse a
        `run_meta.json` already parsed by the caller (the build path parses it once, to filter).
        """
        if metadata is None:
            metadata = StaticsRunMetadata.model_validate_json(
                (statics_output_dir / "run_meta.json").read_text()
            )
        name = BundleName(
            player_name=metadata.capabilities.player_name,
            target=metadata.statics.target,
            fingerprint=metadata.capabilities.fingerprint,
            run_date=metadata.run_date,
        )
        manifest = StaticsSubmission(
            submission_id=name.submission_id,
            measured=metadata.statics,
            submitter=submitter or Submitter(),
            players=[SubmissionPlayer.for_role("defuser", metadata.capabilities)],
            provenance=metadata.provenance,
            run_date=metadata.run_date,
        )
        return cls(
            manifest=manifest, metrics_text=(statics_output_dir / "metrics.json").read_text()
        )

    @override
    def _write_payload(self, bundle_dir: Path) -> None:
        _ = (bundle_dir / self.payload_filename).write_text(self.metrics_text)


def load_submission_bundle(bundle_dir: Path) -> InteractiveBundle | StaticsBundle:
    """Read whichever bundle kind lives at `bundle_dir`.

    Raise on anything malformed.
    """
    manifest = load_submission_manifest(bundle_dir)
    if isinstance(manifest, InteractiveSubmission):
        payload = read_typed_parquet(
            SubmissionExperiment, bundle_dir / InteractiveBundle.payload_filename
        )
        return InteractiveBundle(manifest=manifest, experiments=payload)
    metrics_text = (bundle_dir / StaticsBundle.payload_filename).read_text()
    return StaticsBundle(manifest=manifest, metrics_text=metrics_text)


def load_submission_manifest(bundle_dir: Path) -> InteractiveSubmission | StaticsSubmission:
    """Read and validate a bundle's `submission.yaml`."""
    raw = yaml.safe_load((bundle_dir / "submission.yaml").read_text())
    if not isinstance(raw, dict):
        raise TypeError(f"{bundle_dir / 'submission.yaml'} is not a mapping")
    return parse_submission_manifest(raw)


def _collect_distinct_experts(experiments: list[SubmissionExperiment]) -> list[PlayerCapabilities]:
    """Every distinct expert (by capability fingerprint) paired with the defuser, name-sorted."""
    experts: dict[str, PlayerCapabilities] = {}
    for experiment in experiments:
        if experiment.expert_capabilities is not None:
            experts[experiment.expert_capabilities.fingerprint] = experiment.expert_capabilities
    return sorted(experts.values(), key=lambda capabilities: capabilities.player_name)


def _write_manifest(bundle_dir: Path, manifest: InteractiveSubmission | StaticsSubmission) -> None:
    """Merge preserved fields over any existing manifest, then write `submission.yaml`."""
    manifest_path = bundle_dir / "submission.yaml"

    # Load the existing manifest if it exists
    existing = yaml.safe_load(manifest_path.read_text()) if manifest_path.exists() else None

    # Grab the submitter block from the existing manifest if it exists and merge it with the new
    # manifest we want to write. This is so that we don't overwrite the submitter block and make
    # things more annoying
    if existing and (submitter := existing.get("submitter")) is not None:
        manifest = manifest.model_copy(update={"submitter": Submitter.model_validate(submitter)})

    # Write the manifest
    _ = manifest_path.write_text(
        yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False, default_flow_style=False)
    )
