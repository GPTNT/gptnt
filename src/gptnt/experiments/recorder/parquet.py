"""Read/write experiment player records as Parquet.

One `experiment-{name}-{uuid}.parquet` file per player: step records are the rows (in the
`mode="db"` representation, so they merge straight into DuckDB), and the experiment-level facts —
descriptor, final bomb state, provenance, crash flag, role — live in the parquet footer as a single
validated `RecordFooter` model. A few flat scalar keys (`session_id`, `player_uuid`,
`format_version`) sit alongside it so identity/version reads don't have to parse the whole footer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import pyarrow as pa
from pyarrow import parquet as pq
from pydantic import BaseModel, ConfigDict
from pydantic_ai import RunUsage

# These three are RecordFooter field types — pydantic needs them at runtime to build the model,
# so they can't move into TYPE_CHECKING despite only appearing in annotations.
from gptnt.experiments.descriptor import ExperimentDescriptor  # noqa: TC001
from gptnt.experiments.duckdb import EXPORT_CONTEXT_MARKER, AsBlob, arrow_schema_for
from gptnt.experiments.models import ExperimentPlayerRecord, ExperimentStep
from gptnt.experiments.provenance import ProvenanceMixin
from gptnt.ktane.state.bomb import BombState  # noqa: TC001
from gptnt.specification import PlayerRole  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path
    from typing import Any

# Footer key-value metadata keys (parquet stores bytes -> bytes).
KEY_FOOTER = b"footer"  # the RecordFooter, as JSON
KEY_FORMAT_VERSION = b"format_version"
KEY_SESSION_ID = b"session_id"  # flat, for cheap identity reads (idempotency / grouping)
KEY_PLAYER_UUID = b"player_uuid"

FORMAT_VERSION = b"2"
_ROW_GROUP_SIZE = 64

_STEP_SCHEMA = arrow_schema_for(ExperimentStep)


class RecordFooter(ProvenanceMixin):
    """The validated experiment-level footer of one player's parquet record.

    Provenance comes from [ProvenanceMixin]; the rest is the per-player view of the experiment that
    the recorder has at write time. This is the single contract for the footer — written once, read
    once, validated by pydantic.
    """

    model_config = ConfigDict(frozen=True)

    descriptor: ExperimentDescriptor
    final_bomb_state: BombState | None
    is_hard_crash: bool
    role: PlayerRole


def build_footer(footer: RecordFooter, *, player_uuid: str) -> dict[bytes, bytes]:
    """Assemble the parquet footer KV metadata for one player record."""
    return {
        KEY_FOOTER: footer.model_dump_json().encode(),
        KEY_FORMAT_VERSION: FORMAT_VERSION,
        KEY_SESSION_ID: str(footer.descriptor.session_id).encode(),
        KEY_PLAYER_UUID: player_uuid.encode(),
    }


def footer_from_player_record(record: ExperimentPlayerRecord) -> dict[bytes, bytes]:
    """Build the footer KV directly from a (rebuilt) player record."""
    footer = RecordFooter(
        descriptor=record.experiment_descriptor,
        final_bomb_state=record.final_bomb_state,
        is_hard_crash=record.is_hard_crash,
        role=record.role,
        gptnt_version=record.gptnt_version,
        git_sha=record.git_sha,
    )
    return build_footer(footer, player_uuid=str(record.player_content.uuid))


def write_player_record_parquet(
    *, blobbed_steps: Iterable[dict[str, Any]], footer: dict[bytes, bytes], output_path: Path
) -> None:
    """Write blobbed step dicts as parquet rows with `footer` stamped into the file metadata.

    Rows flush in row-group batches to bound peak memory and keep any single column under the
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
    """Read the raw footer KV metadata (no row data) — for cheap flat-key lookups."""
    metadata = pq.read_schema(path).metadata
    return dict(metadata) if metadata else {}


def read_record_footer(path: Path) -> RecordFooter:
    """Read and validate the typed `RecordFooter`, failing loudly on an unknown format version."""
    raw = read_footer_kv(path)
    version = raw.get(KEY_FORMAT_VERSION)
    if version != FORMAT_VERSION:
        raise ValueError(
            f"Unsupported record footer format_version {version!r} "
            f"(expected {FORMAT_VERSION!r}): {path}"
        )
    return RecordFooter.model_validate_json(raw[KEY_FOOTER])


def read_session_id_from_parquet(path: Path) -> str:
    """Read the experiment session id from its flat key, without parsing the whole footer.

    The flat key exists to keep this cheap. The ingest scan groups every output file by session
    id, so it must not pay a full `RecordFooter` parse per file.
    """
    return read_footer_kv(path)[KEY_SESSION_ID].decode()


class _UsageColumn(BaseModel):
    """One `usage` cell, decoded through the same `AsBlob` codec the step records use."""

    usage: Annotated[RunUsage, AsBlob]


def read_run_usage(path: Path) -> RunUsage:
    """Sum the per-step usage from a player record, reading only the compressed `usage` column.

    Parquet is columnar, so this skips the large `input_messages` / `observation` blobs entirely —
    the usage total is all a submission needs, and re-reading the whole record just to sum it would
    pull megabytes of image bytes per step.
    """
    usage_cells = pq.read_table(path, columns=["usage"]).column("usage").to_pylist()
    return sum(
        (_UsageColumn.model_validate({"usage": cell}).usage for cell in usage_cells), RunUsage()
    )


def load_player_record_from_parquet(path: Path) -> ExperimentPlayerRecord:
    """Reconstruct a full ExperimentPlayerRecord (steps + descriptor + provenance) from parquet."""
    footer = read_record_footer(path)

    table = pq.read_table(path)
    steps = [
        ExperimentStep.model_validate(row, context={"mode": EXPORT_CONTEXT_MARKER})
        for row in table.to_pylist()
    ]
    if not steps:
        raise ValueError(f"Parquet record has no step rows: {path}")

    player_content = footer.descriptor.get_player_content_by_role(steps[0].role)
    return ExperimentPlayerRecord(
        experiment_descriptor=footer.descriptor,
        player_content=player_content,
        step_records=steps,
        is_hard_crash=footer.is_hard_crash,
        gptnt_version=footer.gptnt_version,
        git_sha=footer.git_sha,
    )
