from functools import partial

import anyio
import logfire
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from hypercorn import Config
from hypercorn.asyncio import serve
from redis import Redis
from structlog import get_logger

from gptnt.common.logger import configure_logging
from gptnt.common.servers import get_available_port
from gptnt.ktane.game_settings import KtaneSettings
from gptnt.services.game.lifespan import game_lifespan
from gptnt.services.game.middleware import add_state_headers_to_response
from gptnt.services.game.routes import router

_ = logfire.configure(service_name="game", scrubbing=False)


logger = get_logger()


def run(*, port: int | None = None) -> FastAPI:
    """Create and run the application for the game instance."""
    url = f"http://127.0.0.1:{port}"
    logger.info("Starting game instance", url=url, port=port)

    ktane_settings = KtaneSettings()
    ktane_settings.update_environment_variables()
    ktane_settings.create_settings_files()

    app = FastAPI(
        debug=True, lifespan=partial(game_lifespan, url=url, redis=Redis(decode_responses=True))
    )
    app.include_router(router)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # _ = app.middleware("http")(logging_middleware)
    # app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    # app.add_exception_handler(RequestValidationError, validation_exception_handler)
    # Middleware is run from outer to inner, so we add them in reverse order of execution
    _ = app.middleware("http")(add_state_headers_to_response)

    _ = logfire.instrument_fastapi(app)

    return app


if __name__ == "__main__":
    configure_logging()

    available_port = get_available_port()

    config = Config()
    config.bind = [f"localhost:{available_port}"]
    config.backlog = 1024

    anyio.run(partial(serve, app=run(port=available_port), config=config), backend="asyncio")  # pyright: ignore[reportArgumentType]
