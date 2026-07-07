"""What a submission bundle is, and the one place it gets named and written.

A bundle is one directory per (model, target):

    <output>/<model-slug>_<capfp8>/<target>@<revision>/
        submission.yaml       # the manifest; every derived field regenerated on rebuild
        experiments.parquet   # interactive payload, or
        metrics.json          # statics payload

`BundleName` is the single source of naming (the `submission_id` and the directory), and
`write_bundle` is the only place a bundle directory is created. Rebuilding a bundle regenerates
everything derived but keeps the hand-filled `submitter` block of an existing manifest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from gptnt.cli.config_discovery import player_identities
from gptnt.cli.submission._schema import SubmissionBase, SubmissionPlayer, Submitter

if TYPE_CHECKING:
    from collections.abc import Callable

    from whenever import Instant

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


def _write_manifest(bundle_dir: Path, manifest: SubmissionBase) -> None:
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
        yaml.safe_dump(manifest, sort_keys=False, default_flow_style=False)
    )


def write_bundle[PayloadT](
    output_path: Path,
    name: BundleName,
    manifest: SubmissionBase,
    write_payload_fn: Callable[[Path], PayloadT],
) -> Path:
    """Create the bundle dir, write its payload and the manifest."""
    bundle_dir = output_path / name.relative_dir
    bundle_dir.mkdir(parents=True, exist_ok=True)
    _ = write_payload_fn(bundle_dir)
    _write_manifest(bundle_dir, manifest)
    return bundle_dir
