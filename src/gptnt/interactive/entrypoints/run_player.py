from functools import partial

import anyio
import logfire
from coredis import Redis
from faststream import FastStream
from hydra.utils import instantiate
from pydantic import RedisDsn
from structlog import get_logger

from gptnt.common.hydra import compose_player_config, get_hydra_overrides
from gptnt.common.logger import configure_logging, create_faststream_logger
from gptnt.common.paths import Paths, remove_empty_experiment_recorder_outputs
from gptnt.interactive.services.broker import create_redis_broker
from gptnt.interactive.services.game.client import GameClient
from gptnt.interactive.services.player.message_handler import IncomingMessageHandler
from gptnt.interactive.services.player.service import PlayerService
from gptnt.ktane.manuals.legacy import KtaneManualPaths
from gptnt.observability.settings import ObservabilitySettings
from gptnt.players.configuration import ResolvedPlayerConfig, resolve_player_config

logger = get_logger()

paths = Paths()
ktane_manual_paths = KtaneManualPaths()

observability_settings = ObservabilitySettings()


def load_player_config(hydra_overrides: list[str] | None = None) -> ResolvedPlayerConfig:
    """Compose and resolve the player configuration used by this service process."""
    return resolve_player_config(
        compose_player_config(overrides=hydra_overrides or get_hydra_overrides())
    )


def _instantiate_player_partial(resolved: ResolvedPlayerConfig) -> partial[PlayerService]:
    """Instantiate runtime components before replacing their recorded identity objects."""
    player_partial: partial[PlayerService] = instantiate(resolved.config.player)
    player_partial.keywords["capabilities"] = resolved.capabilities
    player_partial.keywords["identity"] = resolved.identity
    return player_partial


def main(
    *,
    redis_dsn: str | RedisDsn = "redis://localhost:6379",
    hydra_overrides: list[str] | None = None,
) -> FastStream:
    """Create and run the application for the player service."""
    hydra_overrides = hydra_overrides or get_hydra_overrides()

    logger.info("Starting player instance", hydra_overrides=hydra_overrides)
    resolved = load_player_config(hydra_overrides)

    player_partial = _instantiate_player_partial(resolved)

    faststream_logger = create_faststream_logger()

    # Setup Redis for heartbeats
    heartbeat_redis = Redis.from_url(str(redis_dsn), decode_responses=True)
    player_partial.keywords["redis"] = heartbeat_redis

    broker = create_redis_broker(redis_dsn, client_name="player", logger=faststream_logger)

    player_partial.keywords["game_client"] = GameClient(broker=broker)
    player_partial.keywords["incoming_message_handler"] = IncomingMessageHandler(broker=broker)

    player_service = PlayerService(broker=broker, **player_partial.keywords)

    app = FastStream(
        broker,
        lifespan=player_service.lifespan,
        after_shutdown=[logfire.shutdown],
        logger=faststream_logger,  # pyright: ignore[reportArgumentType]
    )
    app.context.set_global("player_service", player_service)

    logger.info("Starting FastStream application")
    return app


if __name__ == "__main__":
    observability_settings.configure("player")

    configure_logging()
    remove_empty_experiment_recorder_outputs(paths.experiment_recorder_dir)
    application = main()
    anyio.run(application.run, backend="asyncio")
