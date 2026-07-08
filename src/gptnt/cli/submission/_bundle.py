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

import pyarrow as pa
import yaml
from pyarrow import parquet as pq

from gptnt.cli.config_discovery import player_identities
from gptnt.cli.submission._schema import (
    InteractiveSubmission,
    StaticsSubmission,
    SubmissionExperiment,
    SubmissionPlayer,
    Submitter,
    SuiteIdentity,
    parse_submission_manifest,
)
from gptnt.experiments.db.schema import EXPORT_CONTEXT_MARKER
from gptnt.experiments.provenance import ProvenanceMixin
from gptnt.statics.run_metadata import StaticsRunMetadata

if TYPE_CHECKING:
    from whenever import Instant

    from gptnt.experiments.suite import Suite
    from gptnt.players.specification import PlayerCapabilities, PlayerRole

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
    """An interactive submission: the manifest plus its `experiments.parquet` rows."""

    experiments: list[SubmissionExperiment]

    payload_filename: ClassVar[str] = "experiments.parquet"

    @classmethod
    def from_experiments(cls, experiments: list[SubmissionExperiment], suite: Suite) -> Self:
        """Bundle one model's rows for one frozen suite (`submitter` stays blank for a human)."""
        canonical = experiments[0]
        measured = SuiteIdentity.from_suite(suite)
        name = BundleName(
            player_name=canonical.defuser_capabilities.player_name,
            target=measured.target,
            fingerprint=canonical.defuser_capabilities.fingerprint,
            run_date=min(row.experiment_descriptor.start_time for row in experiments),
        )
        manifest = InteractiveSubmission(
            submission_id=name.submission_id,
            measured=measured,
            submitter=Submitter(),
            players=[
                create_submission_player_entry("defuser", canonical.defuser_capabilities),
                *(
                    create_submission_player_entry("expert", capabilities)
                    for capabilities in _get_distinct_experts(experiments)
                ),
            ],
            provenance=ProvenanceMixin(
                gptnt_version=canonical.gptnt_version, git_sha=canonical.git_sha
            ),
            run_date=name.run_date,
        )
        return cls(manifest=manifest, experiments=experiments)

    @override
    def _write_payload(self, bundle_dir: Path) -> None:
        write_experiments_payload(self.experiments, file_path=bundle_dir / self.payload_filename)


@dataclass(kw_only=True, frozen=True)
class StaticsBundle(SubmissionBundle[StaticsSubmission]):
    """A statics submission: the manifest plus its verbatim `metrics.json` text."""

    metrics_text: str

    payload_filename: ClassVar[str] = "metrics.json"

    @classmethod
    def from_run_dir(cls, statics_output_dir: Path) -> Self:
        """Bundle one statics run from its outputs dir (`submitter` stays blank for a human).

        The task is read off the stamped `run_meta.json`, not the directory name — the run's own
        metadata is the source of truth for what was measured.
        """
        meta_path = statics_output_dir / "run_meta.json"
        metrics_path = statics_output_dir / "metrics.json"
        if not meta_path.exists() or not metrics_path.exists():
            raise RuntimeError(
                f"{statics_output_dir} is not a statics outputs dir (needs run_meta.json and "
                "metrics.json); run `gptnt statics <task> --throw --dataset-revision <ref>` first."
            )

        metadata = StaticsRunMetadata.model_validate_json(meta_path.read_text())
        name = BundleName(
            player_name=metadata.capabilities.player_name,
            target=metadata.statics.target,
            fingerprint=metadata.capabilities.fingerprint,
            run_date=metadata.run_date,
        )
        manifest = StaticsSubmission(
            submission_id=name.submission_id,
            measured=metadata.statics,
            submitter=Submitter(),
            players=[create_submission_player_entry("defuser", metadata.capabilities)],
            provenance=metadata.provenance,
            run_date=name.run_date,
        )
        return cls(manifest=manifest, metrics_text=metrics_path.read_text())

    @override
    def _write_payload(self, bundle_dir: Path) -> None:
        _ = (bundle_dir / self.payload_filename).write_text(self.metrics_text)


def load_submission_bundle(bundle_dir: Path) -> InteractiveBundle | StaticsBundle:
    """Read whichever bundle kind lives at `bundle_dir`.

    Raise on anything malformed.
    """
    manifest = load_submission_manifest(bundle_dir)
    if isinstance(manifest, InteractiveSubmission):
        payload = read_experiments_payload(bundle_dir / InteractiveBundle.payload_filename)
        return InteractiveBundle(manifest=manifest, experiments=payload)
    metrics_text = (bundle_dir / StaticsBundle.payload_filename).read_text()
    return StaticsBundle(manifest=manifest, metrics_text=metrics_text)


def load_submission_manifest(bundle_dir: Path) -> InteractiveSubmission | StaticsSubmission:
    """Read and validate a bundle's `submission.yaml`."""
    raw = yaml.safe_load((bundle_dir / "submission.yaml").read_text())
    if not isinstance(raw, dict):
        raise TypeError(f"{bundle_dir / 'submission.yaml'} is not a mapping")
    return parse_submission_manifest(raw)


def write_experiments_payload(experiments: list[SubmissionExperiment], *, file_path: Path) -> None:
    """Write the rows to `experiments.parquet` using the model's `db`-context serialization."""
    rows = [
        experiment.model_dump(context={"mode": EXPORT_CONTEXT_MARKER})
        for experiment in experiments
    ]
    _ = pq.write_table(pa.Table.from_pylist(rows), file_path)


def read_experiments_payload(file_path: Path) -> list[SubmissionExperiment]:
    """Read `experiments.parquet` back into typed rows (the JSON columns parse back on input)."""
    table = pq.read_table(file_path)
    return [SubmissionExperiment.model_validate(row) for row in table.to_pylist()]


def create_submission_player_entry(
    role: PlayerRole, capabilities: PlayerCapabilities
) -> SubmissionPlayer:
    """Create a player entry for the submission.

    `identity` is the model's leaderboard attribution from `configs/player/*.yaml`. A submission
    must be attributable, so a model with no `identity` block is a hard error, not a blank entry.
    """
    identity = player_identities().get(capabilities.player_name)
    if identity is None:
        raise ValueError(
            f"No PlayerIdentity for {capabilities.player_name!r}: add an `identity` block to its "
            "configs/player/*.yaml before submitting."
        )
    return SubmissionPlayer(role=role, capabilities=capabilities, identity=identity)


def _get_distinct_experts(rows: list[SubmissionExperiment]) -> list[PlayerCapabilities]:
    """Every distinct expert (by capability fingerprint) paired with the defuser, name-sorted."""
    experts: dict[str, PlayerCapabilities] = {}
    for row in rows:
        if row.expert_capabilities is not None:
            experts[row.expert_capabilities.fingerprint] = row.expert_capabilities
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
