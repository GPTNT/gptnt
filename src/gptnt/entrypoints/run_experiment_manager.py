import asyncio

import anyio
import logfire

from gptnt.common.logger import configure_logging
from gptnt.experiments.experiment_manager.api import ExperimentManagerAPI

_ = logfire.configure(service_name="experiment-manager")
configure_logging()


async def main() -> None:
    """Runs the room forever, gracefully exiting (without zombies!) on Ctrl+C."""
    experiment_manager = ExperimentManagerAPI()
    _ = logfire.instrument_fastapi(experiment_manager.app, excluded_urls=["/health"])
    async with experiment_manager as manager:
        while not manager._should_exit:  # noqa: SLF001
            _ = await asyncio.sleep(delay=1)


anyio.run(func=main)
