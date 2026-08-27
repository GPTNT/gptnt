"""Read/write experiment player records as Parquet.

One `experiment-{name}-{uuid}.parquet` file per player: step records are the rows (in the
`mode="db"` representation, so they merge straight into DuckDB). The experiment-level facts,
including instance, final bomb state, provenance, crash flag, and role, live in the parquet footer
as one validated `RecordFooter` model. A few flat scalar keys (`session_id`, `player_uuid`,
`format_version`) sit beside it so identity/version reads don't have to parse the whole footer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow as pa
from pyarrow import parquet as pq
from pydantic import ConfigDict

from gptnt.experiments.db.schema import EXPORT_CONTEXT_MARKER, arrow_schema_for
from gptnt.experiments.instance import ExperimentInstance  # noqa: TC001
from gptnt.experiments.records import ExperimentPlayerRecord, ExperimentStep
from gptnt.ktane.state.bomb import BombState  # noqa: TC001
from gptnt.players.specification import PlayerRole  # noqa: TC001
from gptnt.provenance import Provenance

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path
    from typing import Any

# Footer key-value metadata keys (parquet stores bytes -> bytes).
KEY_FOOTER = b"footer"  # the RecordFooter, as JSON
KEY_FORMAT_VERSION = b"format_version"
KEY_SESSION_ID = b"session_id"  # flat, for cheap identity reads (idempotency / grouping)
KEY_PLAYER_UUID = b"player_uuid"

FORMAT_VERSION = b"3"
_ROW_GROUP_SIZE = 64

_STEP_SCHEMA = arrow_schema_for(ExperimentStep)


class RecordFooter(Provenance):
    """The experiment-level footer of one player's parquet record.

    The recorder's per-player view of the experiment at write time.
    """

    model_config = ConfigDict(frozen=True)

    instance: ExperimentInstance
    """Execution metadata shared by every row in this player's Parquet file."""

    final_bomb_state: BombState | None
    """Last bomb state captured for the execution."""

    is_hard_crash: bool
    role: PlayerRole
    """Player role whose step rows are stored in the file."""


def build_footer(footer: RecordFooter, *, player_uuid: str) -> dict[bytes, bytes]:
    """Assemble the parquet footer KV metadata for one player record."""
    return {
        KEY_FOOTER: footer.model_dump_json().encode(),
        KEY_FORMAT_VERSION: FORMAT_VERSION,
        KEY_SESSION_ID: str(footer.instance.session_id).encode(),
        KEY_PLAYER_UUID: player_uuid.encode(),
    }


def footer_from_player_record(record: ExperimentPlayerRecord) -> dict[bytes, bytes]:
    """Build the footer KV directly from a (rebuilt) player record."""
    footer = RecordFooter(
        instance=record.experiment_instance,
        final_bomb_state=record.final_bomb_state,
        is_hard_crash=record.is_hard_crash,
        role=record.role,
        gptnt_version=record.gptnt_version,
        release_commit=record.release_commit,
        release_tag=record.release_tag,
        release_protected_content_digest=record.release_protected_content_digest,
        protected_content_digest=record.protected_content_digest,
        protected_content_modified=record.protected_content_modified,
    )
    return build_footer(footer, player_uuid=str(record.player_content.uuid))


def write_player_record_parquet(
    *, blobbed_steps: Iterable[dict[str, Any]], footer: dict[bytes, bytes], output_path: Path
) -> None:
    """Write blobbed step dicts as parquet rows with `footer` stamped into the file metadata.

    Rows flush in row-group batches to bound peak memory and keep any column under the
    `large_binary` offset limit. Written to a sibling `.tmp`, then atomically renamed into place.
    """
    schema = _STEP_SCHEMA.with_metadata(footer)
    tmp_path = output_path.parent / f"{output_path.name}.tmp"

    with pq.ParquetWriter(tmp_path, schema) as writer:
        batch: list[dict[str, Any]] = []

        for step in blobbed_steps:
            batch.append(step)
            if len(batch) >= _ROW_GROUP_SIZE:
                writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                batch = []

        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=schema))

    _ = tmp_path.replace(output_path)


def blob_step(step: ExperimentStep) -> dict[str, Any]:
    """Serialise a step record into its blobbed DuckDB-export dict (one parquet row)."""
    return step.model_dump(context={"mode": EXPORT_CONTEXT_MARKER})


def read_footer_kv(path: Path) -> dict[bytes, bytes]:
    """Read supported footer KV metadata without loading row data."""
    metadata = pq.read_schema(path).metadata
    raw = dict(metadata) if metadata else {}
    version = raw.get(KEY_FORMAT_VERSION)
    if version == b"2":
        raise ValueError(
            f"Record footer format_version 2 is a v1 artifact and requires v1 tooling: {path}"
        )
    if version != FORMAT_VERSION:
        raise ValueError(
            f"Unsupported record footer format_version {version!r} "
            f"(expected {FORMAT_VERSION!r}): {path}"
        )
    return raw


def read_record_footer(path: Path) -> RecordFooter:
    """Read and validate the typed `RecordFooter`."""
    raw = read_footer_kv(path)
    return RecordFooter.model_validate_json(raw[KEY_FOOTER])


def read_session_id_from_parquet(path: Path) -> str:
    """Read the experiment session id from its flat key, without parsing the whole footer.

    The flat key exists to keep this cheap. The ingest scan groups every output file by session
    id, so it must not pay a full `RecordFooter` parse per file.
    """
    return read_footer_kv(path)[KEY_SESSION_ID].decode()


def load_player_record_from_parquet(path: Path) -> ExperimentPlayerRecord:
    """Reconstruct a full player record from its steps, instance, and provenance."""
    footer = read_record_footer(path)

    table = pq.read_table(path)
    steps = [
        ExperimentStep.model_validate(row, context={"mode": EXPORT_CONTEXT_MARKER})
        for row in table.to_pylist()
    ]
    if not steps:
        raise ValueError(f"Parquet record has no step rows: {path}")

    player_content = footer.instance.get_player_content_by_role(steps[0].role)
    return ExperimentPlayerRecord(
        experiment_instance=footer.instance,
        player_content=player_content,
        step_records=steps,
        is_hard_crash=footer.is_hard_crash,
        gptnt_version=footer.gptnt_version,
        release_commit=footer.release_commit,
        release_tag=footer.release_tag,
        release_protected_content_digest=footer.release_protected_content_digest,
        protected_content_digest=footer.protected_content_digest,
        protected_content_modified=footer.protected_content_modified,
    )
