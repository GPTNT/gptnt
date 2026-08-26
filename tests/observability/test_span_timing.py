"""Span timing JSONL serialization."""

from pathlib import Path

from pydantic_core import from_json

from gptnt.observability.span_timing import SpanTimingExporter


def test_timing_rows_remain_utf8_newline_delimited_json(tmp_path: Path) -> None:
    output = tmp_path / "timings.jsonl"
    exporter = SpanTimingExporter(output, service="player")
    row = {
        "service": "player",
        "session_id": "session",
        "player_role": "expert",
        "player_name": "modèle",
        "model_name": "provider:model",
        "game_uuid": "game",
        "trace_id": "trace",
        "span_id": "span",
        "parent_span_id": None,
        "name": "Send request to agent",
        "otel_scope_name": "gptnt",
        "start_ns": 10,
        "end_ns": 20,
        "duration_s": 1e-8,
    }

    exporter._write_rows([row])
    exporter.shutdown()

    encoded = output.read_bytes()
    assert encoded.endswith(b"\n")
    assert len(encoded.splitlines()) == 1
    assert b'"player_name":"mod\xc3\xa8le"' in encoded
    assert from_json(encoded)["player_name"] == "modèle"
