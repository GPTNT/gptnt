import sys
from functools import partial

import anyio
import hydra
import logfire
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from hypercorn import Config
from hypercorn.asyncio import serve
from pydantic import RedisDsn
from redis import Redis
from structlog import get_logger

from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths
from gptnt.common.prompt_cache import PromptCache
from gptnt.common.servers import get_available_port
from gptnt.ktane.manual import KtaneManualPaths
from gptnt.services.player.lifespan import player_lifespan
from gptnt.services.player.routes import router
from gptnt.services.player.supervisor import PlayerSupervisor

_ = logfire.configure(service_name="player", scrubbing=False)

logger = get_logger()

paths = Paths()
ktane_manual_paths = KtaneManualPaths()


def get_hydra_overrides() -> list[str]:
    """Check and return any Hydra overrides passed as command line arguments."""
    hydra_overrides = sys.argv[1:] if len(sys.argv) > 1 else []
    if hydra_overrides:
        logger.debug(f"Hydra overrides: {hydra_overrides}")
    return hydra_overrides


def run(
    *,
    port: int | None = None,
    redis_dsn: RedisDsn | None = None,
    hydra_overrides: list[str] | None = None,
) -> FastAPI:
    """Create and run the application for the player service."""
    PromptCache.initialise(
        paths.prompts, ktane_manual_paths.text_dir, ktane_manual_paths.images_small_dir
    )

    url = f"http://127.0.0.1:{port}"
    hydra_overrides = hydra_overrides or get_hydra_overrides()

    logger.info("Starting player instance", url=url, port=port, hydra_overrides=hydra_overrides)
    with hydra.initialize_config_dir(version_base="1.3", config_dir=str(paths.configs)):
        config = hydra.compose(config_name="player.yaml", overrides=hydra_overrides)

    # Instantiate the player from the class
    player_partial = hydra.utils.instantiate(config.player)
    player_partial.keywords["url"] = str(url)
    if redis_dsn is not None:
        player_partial.keywords["redis"] = Redis.from_url(str(redis_dsn), decode_responses=True)

    logger.info("Instantiating player supervisor", url=url)
    player = player_partial()
    assert isinstance(player, PlayerSupervisor)

    app = FastAPI(debug=True, lifespan=partial(player_lifespan, player_supervisor=player))
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

    available_port = get_available_port()

    config = Config()
    config.bind = [f"localhost:{available_port}"]
    config.backlog = 1024

    anyio.run(partial(serve, app=run(port=available_port), config=config), backend="asyncio")  # pyright: ignore[reportArgumentType]
