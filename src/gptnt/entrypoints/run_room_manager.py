from functools import partial

import logfire
import structlog
from fastapi import FastAPI

from gptnt.api.room_endpoints import lifespan, router
from gptnt.common.logger import configure_logging
from gptnt.common.servers import get_available_port
from gptnt.ktane.game_settings import KtaneGameSettings, KtanePlayerSettings

_ = logfire.configure(service_name="room-manager", scrubbing=False)
configure_logging()
logfire.instrument_system_metrics(
    config={
        "process.cpu.utilization": None,
        "process.memory.usage": None,
        "process.memory.virtual": None,
        "process.open_file_descriptor.count": None,
        "process.thread.count": None,
        "system.disk.io": ["read", "write"],
        "system.memory.utilization": ["available"],
        "system.disk.operations": ["read", "write"],
        "system.network.errors": ["transmit", "receive"],
    }
)
_logger = structlog.get_logger()


api_port = get_available_port()


def run() -> FastAPI:
    """Runs the room forever, gracefully exiting (without zombies!) on Ctrl+C."""
    # Update KTANE settings
    KtaneGameSettings().update_environment_variables()
    KtanePlayerSettings().create_settings_file()

    # Run the game
    app = FastAPI(lifespan=partial(lifespan, api_host="localhost", api_port=api_port))
    app.include_router(router)
    _ = logfire.instrument_fastapi(app, excluded_urls=["/health"])
    return app


if __name__ == "__main__":
    import uvicorn

    app = run()

    uvicorn.run(app, host="localhost", port=api_port, log_level="warning", timeout_keep_alive=60)
    _logger.info("App closed")
