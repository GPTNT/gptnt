from functools import partial

import anyio
import logfire
from coredis import Redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from hypercorn import Config
from hypercorn.asyncio import serve
from pydantic import RedisDsn
from structlog import get_logger

from gptnt.core.common.logger import configure_logging, create_faststream_logger
from gptnt.core.observability.settings import ObservabilitySettings
from gptnt.core.runtime_settings import RuntimeSettings
from gptnt.interactive.services.broker import create_redis_broker
from gptnt.interactive.services.experiment_manager.api import lifespan, router
from gptnt.interactive.services.experiment_manager.experiment_manager import ExperimentManager

logger = get_logger()
observability_settings = ObservabilitySettings()
runtime_settings = RuntimeSettings()


def run(redis_dsn: RedisDsn | None = None) -> FastAPI:
    """Run an experiment manager."""
    faststream_logger = create_faststream_logger()

    redis_dsn = redis_dsn or runtime_settings.redis_dsn
    redis = Redis.from_url(str(redis_dsn), decode_responses=True)
    redis_broker = create_redis_broker(
        redis_dsn, client_name="experiment_manager", logger=faststream_logger
    )

    experiment_manager = ExperimentManager(redis=redis, redis_broker=redis_broker)

    app = FastAPI(debug=True, lifespan=partial(lifespan, experiment_manager=experiment_manager))
    app.include_router(router)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if observability_settings.instrument_fastapi:
        _ = logfire.instrument_fastapi(app)
    return app


if __name__ == "__main__":
    observability_settings.configure("experiment_manager")
    configure_logging()
    config = Config()
    config.bind = [f"{runtime_settings.em_host}:{runtime_settings.em_port}"]
    config.backlog = 1024

    anyio.run(partial(serve, app=run(), config=config), backend="asyncio")  # pyright: ignore[reportArgumentType]
