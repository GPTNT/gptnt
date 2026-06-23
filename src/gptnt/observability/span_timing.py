"""Capture OpenTelemetry/logfire span durations to disk for benchmark-overhead analysis.

In async mode the experiment wall-clock budget is shared between model inference and the benchmark
harness (observation fetch/render, Set-of-Marks, input building, action dispatch). Every phase is
already wrapped in a named logfire span, but the player/game processes run `logfire.configure(...,
send_to_logfire=False)` with no exporter attached, so those span durations are discarded.

This module provides a :class:`SpanTimingExporter` that appends the durations of an allowlisted set
of spans to a per-process JSONL file. Attaching it as an `additional_span_processor` is behaviour-
neutral and gated behind `ObservabilitySettings.capture_span_timings` (off by default), so normal
runs are unchanged and the measurement does not affect the wall-clock.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, TextIO, TypedDict, override

import structlog
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import format_span_id, format_trace_id

from gptnt.common.paths import Paths

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor

logger = structlog.get_logger()


# The span we wrap `PlayerService.forward_pass` in — the per-step denominator (player process).
PLAYER_FORWARD_PASS_SPAN = "player forward pass"  # noqa: S105

# The span wrapping `agent.run()` — captures the full pydantic-ai round-trip including framework
# overhead. Everything inside this span but outside the pydantic-ai "chat *" spans is overhead.
INFERENCE_SPAN = "Send request to agent"

# pydantic-ai instrumentation scope — "chat *" spans from this scope are the actual LLM calls.
PYDANTIC_AI_SCOPE = "pydantic-ai"

# Named spans we persist: the per-step denominator, the inference span, and the non-inference
# phases that make up the overhead (player-side game-client waits + input prep + dispatch).
# Set-of-Marks internals are children of "Prepare frames" and are intentionally not listed
# individually to keep the files bounded; "Prepare frames" already subsumes their duration.
ALLOWLIST: frozenset[str] = frozenset(
    (
        PLAYER_FORWARD_PASS_SPAN,
        INFERENCE_SPAN,
        "Get observation",
        "Get frames",
        "Build agent input",
        "Adding observations to defuser input",
        "Prepare frames",
        "Applying set of marks on last frame",
        "Saving images back to bytes",
        "Send game action",
        "Send message",
        "Send dialogue message",
        "Do nothing action",
    )
)


@dataclass
class _TimingIdentity:
    """Process-wide experiment identity stamped onto every captured span row.

    Each player/game process handles essentially one experiment for its whole lifetime, so a single
    module-level instance is sufficient and avoids threading identity through every span. Populated
    once from the service's "configure for experiment" handler via :func:`set_timing_identity`; any
    field left unset is written as `null`.
    """

    session_id: str | None = None
    player_role: str | None = None
    player_name: str | None = None
    model_name: str | None = None
    game_uuid: str | None = None


# The live identity for this process. Mutated in place by `set_timing_identity` and read by
# `SpanTimingExporter._row`; there is exactly one experiment per process so no locking is needed.
_IDENTITY = _TimingIdentity()
_IDENTITY_FIELDS: frozenset[str] = frozenset(field.name for field in fields(_TimingIdentity))


def set_timing_identity(**updates: str | None) -> None:
    """Record the current process's experiment identity for subsequent span rows.

    Accepts any subset of the :class:`_TimingIdentity` fields (`session_id`, `player_role`,
    `player_name`, `model_name`, `game_uuid`) as keyword arguments. Unknown keys are ignored so
    callers can pass through whatever context they have without coupling to this schema.
    """
    for key, identity_value in updates.items():
        if key in _IDENTITY_FIELDS:
            setattr(_IDENTITY, key, identity_value)


class _TimingRow(TypedDict):
    """One persisted JSONL record: the identity plus the span's timing and provenance."""

    service: str
    session_id: str | None
    player_role: str | None
    player_name: str | None
    model_name: str | None
    game_uuid: str | None
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    otel_scope_name: str | None
    start_ns: int
    end_ns: int
    duration_s: float


def _is_captured(span: ReadableSpan) -> bool:
    """Return True for spans that should be persisted to the timing file.

    Captures both the explicit allowlist (player/game spans) and pydantic-ai "chat *" spans, which
    represent the actual LLM call inside `agent.run()`.
    Overhead = duration("Send request to agent") - sum(pydantic-ai "chat *" durations).
    """
    if span.name in ALLOWLIST:
        return True
    scope = span.instrumentation_scope
    return scope is not None and scope.name == PYDANTIC_AI_SCOPE and span.name.startswith("chat ")


class SpanTimingExporter(SpanExporter):
    """Append the durations of allowlisted spans to a per-process JSONL file (one object per span).

    Each process writes to its own append-only file (`{service}-{pid}.jsonl`), so concurrent
    player/game processes never fight a shared writer.

    Why the file handle is opened once and held open for the process lifetime, rather than
    reopened on each export:

    - `SimpleSpanProcessor` (see :func:`build_span_timing_processor`) calls :meth:`export`
      *synchronously, on the thread that just ended the span*. That thread is the one whose
      wall-clock this module exists to measure, so the export path must add as little latency
      as possible. Re-`open()`/`close()`-ing the file on every span end would charge a syscall
      pair to the measured thread — and because a child span's export runs *inside* its still-
      open parent span's window, that cost would leak into the parent's recorded duration.
      Holding the handle open reduces each export to a buffered `write` + `flush`.
    - The handle is opened lazily on the first matching span (:meth:`_ensure_writer`), so a
      process that never emits a captured span creates no empty file.

    Durability: each export ends with `flush()`, pushing rows into the OS page cache where they
    survive a non-graceful process exit (only a kernel panic / power loss could lose them).
    :meth:`shutdown` closes the handle on graceful teardown.
    """

    def __init__(self, path: Path, *, service: str) -> None:
        self._path = path
        self._service = service
        # Opened lazily by `_ensure_writer` on the first captured span, then kept open.
        self._writer: TextIO | None = None

    @override
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Write the durations of any allowlisted spans in this batch to the JSONL file."""
        rows = [
            row for span in spans if _is_captured(span) and (row := self._row(span)) is not None
        ]
        if not rows:
            return SpanExportResult.SUCCESS

        try:
            self._write_rows(rows)
        except OSError:
            logger.warning("Failed to write span timings", path=str(self._path))
            return SpanExportResult.FAILURE

        return SpanExportResult.SUCCESS

    @override
    def shutdown(self) -> None:
        """Close the underlying file handle on graceful teardown."""
        if self._writer is not None:
            self._writer.close()
            self._writer = None

    @override
    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Flush any buffered rows to the OS so an external reader sees them promptly."""
        if self._writer is not None:
            self._writer.flush()
        return True

    def _row(self, span: ReadableSpan) -> _TimingRow | None:
        """Project a span into a persisted row, or `None` if it lacks a context / timing."""
        context = span.context
        if context is None or span.start_time is None or span.end_time is None:
            return None

        parent = span.parent
        scope = span.instrumentation_scope
        return {
            "service": self._service,
            "session_id": _IDENTITY.session_id,
            "player_role": _IDENTITY.player_role,
            "player_name": _IDENTITY.player_name,
            "model_name": _IDENTITY.model_name,
            "game_uuid": _IDENTITY.game_uuid,
            "trace_id": format_trace_id(context.trace_id),
            "span_id": format_span_id(context.span_id),
            "parent_span_id": None if parent is None else format_span_id(parent.span_id),
            "name": span.name,
            "otel_scope_name": None if scope is None else scope.name,
            "start_ns": span.start_time,
            "end_ns": span.end_time,
            "duration_s": (span.end_time - span.start_time) / 1e9,
        }

    def _ensure_writer(self) -> TextIO:
        """Return the open append handle, creating the parent dir and opening it on first use."""
        if self._writer is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._writer = self._path.open("a", encoding="utf-8")
        return self._writer

    def _write_rows(self, rows: list[_TimingRow]) -> None:
        """Append `rows` as newline-delimited JSON and flush so they survive a hard exit."""
        writer = self._ensure_writer()
        for row in rows:
            _ = writer.write(f"{json.dumps(row)}\n")
        writer.flush()


def build_span_timing_processor(*, service: str) -> SpanProcessor | None:
    """Build a span processor that captures timings for `service`, or `None` if disabled.

    Returns `None` (zero overhead) unless `settings.capture_span_timings` is set. Uses a
    :class:`~opentelemetry.sdk.trace.export.SimpleSpanProcessor` so rows flush on span-end and
    survive a non-graceful process exit.
    """
    path = Paths().span_timings_dir.joinpath(f"{service}-{os.getpid()}.jsonl")
    return SimpleSpanProcessor(SpanTimingExporter(path, service=service))
