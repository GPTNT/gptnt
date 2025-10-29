from typing import Any

from faststream.redis import RedisBroker
from faststream.redis.opentelemetry import RedisTelemetryMiddleware
from pydantic import RedisDsn

from gptnt.services.exceptions import exc_middleware, exception_aware_decoder


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
    kwargs["middlewares"] = [
        RedisTelemetryMiddleware(),
        exc_middleware,
        *kwargs.get("middlewares", []),
    ]

    return RedisBroker(str(url), **kwargs)
