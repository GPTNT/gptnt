from functools import partial

import anyio
import logfire
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from hypercorn import Config
from hypercorn.asyncio import serve
from pydantic import RedisDsn
from structlog import get_logger

from gptnt.common.logger import configure_logging
from gptnt.services.experiment_manager.experiment_manager import ExperimentManager
from gptnt.services.experiment_manager.lifespan import lifespan
from gptnt.services.experiment_manager.routes import router

_ = logfire.configure(service_name="experiment_manager", scrubbing=False)
logger = get_logger()

EM_PORT = 8085


def run(redis_dsn: RedisDsn | None = None) -> FastAPI:
    """Run an experiment manager."""
    redis_dsn = redis_dsn or RedisDsn("redis://localhost:6379")
    experiment_manager = ExperimentManager(redis_url=redis_dsn)

    app = FastAPI(debug=True, lifespan=partial(lifespan, experiment_manager=experiment_manager))
    app.include_router(router)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _ = logfire.instrument_fastapi(app)
    return app


if __name__ == "__main__":
    configure_logging()
    config = Config()
    config.bind = [f"localhost:{EM_PORT}"]
    config.backlog = 1024

    anyio.run(partial(serve, app=run(), config=config), backend="asyncio")  # pyright: ignore[reportArgumentType]
