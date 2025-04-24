from functools import partial

import logfire
import structlog
from fastapi import FastAPI

from gptnt.api.room_endpoints import lifespan, router
from gptnt.common.hosting import get_available_port
from gptnt.common.logger import configure_logging

_ = logfire.configure(service_name="room-manager")
configure_logging()

_logger = structlog.get_logger()


api_port = get_available_port()


def run() -> FastAPI:
    """Runs the room forever, gracefully exiting (without zombies!) on Ctrl+C."""
    app = FastAPI(lifespan=partial(lifespan, api_host="localhost", api_port=api_port))
    app.include_router(router)
    _ = logfire.instrument_fastapi(app, excluded_urls=["/health"])
    return app


if __name__ == "__main__":
    import uvicorn

    app = run()

    uvicorn.run(app, host="localhost", port=api_port, log_level="warning")
    _logger.info("App closed")
