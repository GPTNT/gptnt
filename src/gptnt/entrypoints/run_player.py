import asyncio
import sys

import hydra
import logfire
from faststream import ExceptionMiddleware
from faststream.app import FastStream
from faststream.rabbit import RabbitBroker
from faststream.rabbit.opentelemetry import RabbitTelemetryMiddleware
from opentelemetry.sdk.trace.sampling import ParentBased
from structlog import get_logger

from gptnt.common.instrumentation import HeartbeatFilterSampler
from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths
from gptnt.common.prompt_cache import PromptCache
from gptnt.ktane.manual import KtaneManualPaths
from gptnt.players.base_player import BasePlayer

_ = logfire.configure(
    service_name="player",
    scrubbing=False,
    sampling=logfire.SamplingOptions(head=ParentBased(HeartbeatFilterSampler())),
)

configure_logging()
_logger = get_logger()

paths = Paths()
ktane_manual_paths = KtaneManualPaths()

exc_middleware = ExceptionMiddleware()


@exc_middleware.add_handler(Exception, publish=True)
def error_handler(exc: Exception) -> None:
    """Handle exceptions raised in the player from handlers."""
    _logger.exception("An error occurred in the player", exc_info=exc)
    sys.exit(1)


async def run_player(*, hydra_overrides: list[str]) -> None:
    """Run the player."""
    PromptCache.initialise(
        paths.prompts, ktane_manual_paths.text_dir, ktane_manual_paths.images_512_dir
    )
    with hydra.initialize_config_dir(version_base="1.3", config_dir=str(paths.configs)):
        config = hydra.compose(config_name="player.yaml", overrides=hydra_overrides)
    # Instantiate the player from the class
    player_partial = hydra.utils.instantiate(config.player)

    broker = RabbitBroker(logger=None, middlewares=(RabbitTelemetryMiddleware(), exc_middleware))
    player_partial.keywords["broker"] = broker
    player = player_partial()
    assert isinstance(player, BasePlayer)

    app = FastStream(player.broker, lifespan=player.lifespan, logger=None)

    # Run the FastStream app until manual exit
    await app.run()


if __name__ == "__main__":
    hydra_overrides = sys.argv[1:] if len(sys.argv) > 1 else []
    if hydra_overrides:
        _logger.debug(f"Hydra overrides: {hydra_overrides}")
    loop = asyncio.new_event_loop()
    loop.run_until_complete(run_player(hydra_overrides=hydra_overrides))
