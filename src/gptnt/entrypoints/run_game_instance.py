import uuid

import anyio
import logfire
import structlog
from coredis import Redis
from faststream import FastStream
from pydantic import RedisDsn

from gptnt.common.logger import configure_logging, create_faststream_logger
from gptnt.ktane.game_settings import KtaneSettings
from gptnt.services.broker import create_redis_broker
from gptnt.services.game.service import GameService

logger = structlog.get_logger()


def main(*, redis_dsn: str | RedisDsn = "redis://localhost:6379") -> FastStream:
    """Create and run the application for the game instance."""
    service_uuid = uuid.uuid4()

    logger.info("Starting game instance", uuid=service_uuid)

    ktane_settings = KtaneSettings()
    ktane_settings.update_environment_variables()
    ktane_settings.create_settings_files()

    faststream_logger = create_faststream_logger()

    heartbeat_redis = Redis.from_url(str(redis_dsn), decode_responses=True)
    broker = create_redis_broker(redis_dsn, client_name="game", logger=faststream_logger)

    game_service = GameService(broker=broker, redis=heartbeat_redis, uuid=service_uuid)

    app = FastStream(
        broker,
        lifespan=game_service.lifespan,
        after_shutdown=[logfire.shutdown],
        logger=faststream_logger,  # pyright: ignore[reportArgumentType]
    )
    app.context.set_global("game_service", game_service)
    return app


if __name__ == "__main__":
    _ = logfire.configure(service_name="game", scrubbing=False)

    configure_logging()
    application = main()
    anyio.run(application.run, backend="asyncio")
