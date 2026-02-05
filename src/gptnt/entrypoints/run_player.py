import anyio
import hydra
import logfire
from faststream import FastStream
from pydantic import RedisDsn
from redis import Redis
from structlog import get_logger

from gptnt.common.hydra import get_hydra_overrides
from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths, remove_empty_experiment_recorder_outputs
from gptnt.ktane.manual import KtaneManualPaths
from gptnt.services.broker import create_redis_broker
from gptnt.services.player.controller import PlayerController

_ = logfire.configure(service_name="player", scrubbing=False)

logger = get_logger()

paths = Paths()
ktane_manual_paths = KtaneManualPaths()


def main(
    *,
    redis_dsn: str | RedisDsn = "redis://localhost:6379",
    hydra_overrides: list[str] | None = None,
) -> FastStream:
    """Create and run the application for the player service."""
    hydra_overrides = hydra_overrides or get_hydra_overrides()

    logger.info("Starting player instance", hydra_overrides=hydra_overrides)
    with hydra.initialize_config_dir(version_base="1.3", config_dir=str(paths.configs)):
        config = hydra.compose(config_name="player.yaml", overrides=hydra_overrides)

    # Instantiate the player from the class
    player_partial = hydra.utils.instantiate(config.player)

    # Setup Redis for heartbeats
    heartbeat_redis = Redis.from_url(str(redis_dsn), decode_responses=True)
    player_partial.keywords["redis"] = heartbeat_redis

    broker = create_redis_broker(redis_dsn, client_name="player")

    logger.info("Instantiating player controller")
    player_controller = PlayerController(**player_partial.keywords, broker=broker)

    app = FastStream(
        broker, lifespan=player_controller.lifespan, after_shutdown=[logfire.shutdown]
    )
    app.context.set_global("player_controller", player_controller)

    logger.info("Starting FastStream application")
    return app


if __name__ == "__main__":
    configure_logging()
    remove_empty_experiment_recorder_outputs(paths.experiment_recorder)
    application = main()
    anyio.run(application.run, backend="asyncio")
