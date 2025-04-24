import logfire
import structlog
from fastapi import FastAPI

from gptnt.api.experiment_manager_routes import lifespan, router
from gptnt.common.logger import configure_logging

_ = logfire.configure(service_name="experiment-manager")
configure_logging()

_logger = structlog.get_logger()


def run() -> FastAPI:
    """Runs the room forever, gracefully exiting (without zombies!) on Ctrl+C."""
    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    _ = logfire.instrument_fastapi(app, excluded_urls=["/health"])
    return app


if __name__ == "__main__":
    import uvicorn

    app = run()

    uvicorn.run(app, host="localhost", port=8099, log_level="warning")  # noqa: WPS432
    _logger.info("App closed")
