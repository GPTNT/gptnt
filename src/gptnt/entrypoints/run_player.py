import asyncio
import sys
from typing import TYPE_CHECKING

import hydra
import logfire
from faststream.app import FastStream
from opentelemetry.sdk.trace.sampling import ParentBased
from structlog import get_logger

from gptnt.common.instrumentation import HeartbeatFilterSampler
from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths
from gptnt.common.prompt_cache import PromptCache
from gptnt.ktane.manual import KtaneManualPaths
from gptnt.players.base_player import BasePlayer

if TYPE_CHECKING:
    from gptnt.players.ai_player import AIPlayer


_ = logfire.configure(
    service_name="player",
    scrubbing=False,
    sampling=logfire.SamplingOptions(head=ParentBased(HeartbeatFilterSampler())),
)

configure_logging()
_logger = get_logger()

paths = Paths()
ktane_manual_paths = KtaneManualPaths()


async def run_player(*, hydra_overrides: list[str]) -> None:
    """Run the player."""
    PromptCache.initialise(
        paths.prompts, ktane_manual_paths.text_dir, ktane_manual_paths.images_512_dir
    )
    with hydra.initialize_config_dir(version_base="1.3", config_dir=str(paths.configs)):
        config = hydra.compose(config_name="player.yaml", overrides=hydra_overrides)
    # Instantiate the player from the class
    player: AIPlayer = hydra.utils.instantiate(config.player)
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
