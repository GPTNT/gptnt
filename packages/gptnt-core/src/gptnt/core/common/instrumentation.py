import abc
from typing import TYPE_CHECKING, Any

import logfire
import structlog
from opentelemetry.sdk.trace import SpanProcessor
from pydantic_settings import BaseSettings, SettingsConfigDict

from gptnt.core.common.span_timing import build_span_timing_processor

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger()


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
    `gptnt.core.common.span_timing`.
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


class PostInitMeta(abc.ABCMeta):
    """Metaclass that automatically calls a `post_init` method, if it exists.

    This pattern defines a post-initialisation logic in a clean and reusable way,
    similar to `__post_init__` in dataclasses, but for any class.

    Inherits from `abc.ABCMeta` so you can also declare abstract methods.
    """

    def __new__(
        mcs: type[type], name: str, bases: tuple[type, ...], namespace: dict[str, Any]
    ) -> type:
        """Create a new class with the metaclass."""
        orig_init: Callable[..., None] | None = namespace.get("__init__")

        def __init__(self: Any, *args: Any, **kwargs: Any) -> None:  # noqa: N807, WPS430
            """Replacement __init__ that calls the original __init__ and then self.post_init()."""
            # If the original __init__ exists, call it with the same arguments
            if orig_init is not None:  # noqa: WPS504
                orig_init(self, *args, **kwargs)

            # Otherwise, call the superclass __init__ method instead
            else:
                super(cls, self).__init__(*args, **kwargs)  # noqa: WPS608

            # Automatically call post_init if it exists
            if hasattr(self, "post_init") and callable(self.post_init):
                _ = self.post_init()

        # Replace the original __init__ with the new one. Bit of a hack, but it works.
        namespace["__init__"] = __init__

        # Create the class using the modified namespace
        cls = super().__new__(  # noqa: WPS117
            mcs,
            name,  # pyright: ignore[reportCallIssue]
            bases,
            namespace,
        )
        return cls
