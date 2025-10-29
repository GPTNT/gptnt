import uuid

import anyio
import logfire
from faststream import FastStream
from pydantic import RedisDsn
from redis import Redis
from structlog import get_logger

from gptnt.common.logger import configure_logging
from gptnt.ktane.game_settings import KtaneSettings
from gptnt.services.broker import create_redis_broker
from gptnt.services.game.controller import GameController

_ = logfire.configure(service_name="game", scrubbing=False)

logger = get_logger()


def main(*, redis_dsn: str | RedisDsn = "redis://localhost:6379") -> FastStream:
    """Create and run the application for the game instance."""
    service_uuid = uuid.uuid4()

    logger.info("Starting game instance", uuid=service_uuid)

    ktane_settings = KtaneSettings()
    ktane_settings.update_environment_variables()
    ktane_settings.create_settings_files()

    heartbeat_redis = Redis.from_url(str(redis_dsn), decode_responses=True)
    broker = create_redis_broker(redis_dsn, client_name="game")
    game_controller = GameController(redis=heartbeat_redis, uuid=service_uuid, broker=broker)

    app = FastStream(broker, lifespan=game_controller.lifespan)
    app.context.set_global("game_controller", game_controller)
    return app


if __name__ == "__main__":
    configure_logging()
    application = main()
    anyio.run(application.run, backend="asyncio")
