from typing import Any

from faststream.redis import RedisBroker
from faststream.redis.opentelemetry import RedisTelemetryMiddleware
from pydantic import RedisDsn

from gptnt.common.instrumentation import ObservabilitySettings
from gptnt.services.exceptions import exc_middleware, exception_aware_decoder

observability_settings = ObservabilitySettings()


def create_redis_broker(url: str | RedisDsn, **kwargs: Any) -> RedisBroker:
    """Create a Redis broker instance with exception handling and telemetry.

    All brokers created with this function automatically:
    - Handle exceptions via ExceptionMiddleware
    - Reconstruct and raise exceptions from RPC responses
    - Include telemetry for observability

    Args:
        url: Redis connection URL
        **kwargs: Additional arguments passed to RedisBroker

    Returns:
        Configured RedisBroker instance
    """
    # Add custom decoder for exception reconstruction
    kwargs["decoder"] = exception_aware_decoder

    # Add middlewares
    kwargs["middlewares"] = [exc_middleware, *kwargs.get("middlewares", [])]

    if observability_settings.instrument_faststream:
        kwargs["middlewares"].append(RedisTelemetryMiddleware())

    return RedisBroker(str(url), **kwargs)
