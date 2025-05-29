import asyncio
from uuid import uuid4

import logfire
from faststream.app import FastStream
from faststream.rabbit import RabbitBroker
from faststream.rabbit.opentelemetry import RabbitTelemetryMiddleware
from opentelemetry.sdk.trace.sampling import ParentBased
from structlog import get_logger

from gptnt.api.game_manager.game_instance import GameInstance
from gptnt.api.rabbit.exceptions import create_exc_middleware
from gptnt.common.instrumentation import HeartbeatFilterSampler
from gptnt.common.logger import configure_logging
from gptnt.ktane.game_settings import KtaneSettings

_ = logfire.configure(
    service_name="game",
    scrubbing=False,
    sampling=logfire.SamplingOptions(head=ParentBased(HeartbeatFilterSampler())),
)


configure_logging()
logger = get_logger()


async def run_game_instance() -> None:
    """Run a game instance."""
    with logfire.span("Start game instance"):
        with logfire.span("Set KTANE settings"):
            ktane_settings = KtaneSettings()
            ktane_settings.create_settings_files()
            ktane_settings.update_environment_variables()

        broker = RabbitBroker(
            logger=None, middlewares=(RabbitTelemetryMiddleware(), create_exc_middleware())
        )
        game_manager = GameInstance(broker=broker, uuid=uuid4())
        app = FastStream(broker, lifespan=game_manager.lifespan, logger=None)

    # Run the FastStream app until manual exit
    await app.run()


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(run_game_instance())
