from __future__ import annotations

from typing import TYPE_CHECKING, Self

import logfire
import structlog
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from gptnt.core.observability.span_timing import build_span_timing_processor

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import SpanProcessor

logger = structlog.get_logger()

# The instrumentation flags rendered into env vars for spawned subprocesses (`to_env`). Excludes
# `capture_span_timings` (an orthogonal benchmark opt-in) and `otel_endpoint` (not a flag).
_INSTRUMENTATION_FIELDS = (
    "enable_metrics",
    "instrument_fastapi",
    "instrument_faststream",
    "instrument_httpx",
    "instrument_pydantic_ai",
    "instrument_redis",
)


class ObservabilitySettings(BaseSettings):
    """Settings for observability and instrumentation.

    This allows us to control whether we enable/disable instrumentation across the codebase from a
    single place. We don't always need everything when we are doing the big throws because that is
    just waaaay too many spans and is just entirely unmanageable/costly/unnecessary.
    """

    model_config = SettingsConfigDict(env_prefix="OBSERVABILITY_")

    enable_metrics: bool = True

    instrument_fastapi: bool = True
    instrument_faststream: bool = True
    instrument_httpx: bool = True
    instrument_pydantic_ai: bool = True
    instrument_redis: bool = False

    capture_span_timings: bool = False
    """Capture per-step span durations to JSONL for benchmark-overhead analysis (off by default).

    When enabled, the player/game processes write inference-vs-overhead timing rows alongside the
    experiment records. Query them with `gptnt timing <run_dir>`. See
    `gptnt.core.observability.span_timing`.
    """

    otel_endpoint: str = Field(
        default="http://localhost:4318/", validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    """Where the OTLP collector is expected.

    Kept on the external OTel var name, not the `OBSERVABILITY_` prefix, since the exporter SDK
    reads it directly.
    """

    def instrument_all(self) -> None:
        """Perform instrumentation based on the settings."""
        if self.instrument_pydantic_ai:
            logfire.instrument_pydantic_ai()
        if self.instrument_httpx:
            logfire.instrument_httpx(
                capture_headers=True, capture_request_body=True, capture_response_body=False
            )
        if self.instrument_redis:
            logfire.instrument_redis()

    def span_processors(self, service_name: str) -> list[SpanProcessor]:
        """Extra span processors to pass to `logfire.configure` for `service_name`."""
        # Imported lazily: span_timing pulls in the OTel SDK, only needed when capturing.

        processors = []
        if self.capture_span_timings:
            processors.append(build_span_timing_processor(service=service_name))
        return processors

    def configure(self, service_name: str) -> None:
        """Configure logfire for `service_name` and apply instrumentation.

        The one place every entrypoint (player/game/experiment_manager) configures logfire, so the
        configuration can't drift between them.
        """
        _ = logfire.configure(
            service_name=service_name,
            scrubbing=False,
            send_to_logfire=False,
            distributed_tracing=True,
            additional_span_processors=self.span_processors(service_name),
        )
        self.instrument_all()

    def to_env(self) -> dict[str, str]:
        """Render the instrumentation flags as `OBSERVABILITY_*` env vars for spawned subprocesses.

        The flag names live only on this class, so the spawn pipeline's presets can't drift from
        the settings the subprocess reads back.
        """
        return {
            f"OBSERVABILITY_{name.upper()}": str(getattr(self, name)).lower()
            for name in _INSTRUMENTATION_FIELDS
        }

    @classmethod
    def limited(cls) -> Self:
        """Minimal instrumentation for big throws: pydantic-ai spans only, no metrics."""
        return cls(
            enable_metrics=False,
            instrument_fastapi=False,
            instrument_faststream=False,
            instrument_httpx=False,
            instrument_pydantic_ai=True,
            instrument_redis=False,
        )

    @classmethod
    def off(cls) -> Self:
        """All instrumentation disabled."""
        return cls(
            enable_metrics=False,
            instrument_fastapi=False,
            instrument_faststream=False,
            instrument_httpx=False,
            instrument_pydantic_ai=False,
            instrument_redis=False,
        )
