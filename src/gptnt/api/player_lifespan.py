import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from gptnt.api.experiment_manager_client import ExperimentManagerClient
from gptnt.api.structures import PlayerMetadata
from gptnt.players.base_player import BasePlayer

logger = structlog.get_logger()


@asynccontextmanager
async def player_lifespan(
    app: FastAPI,
    player: BasePlayer,
    experiment_manager_client: ExperimentManagerClient,
    api_info: PlayerMetadata,
) -> AsyncGenerator[None]:
    """Lifespan context manager for PlayerAPI."""
    logger.info("Starting PlayerAPI", api_info=api_info)

    # Set up the player and experiment manager client in the app state
    app.state.player = player

    app.state.experiment_manager_client = await experiment_manager_client.start()

    # Start the main loop task for the player, if one exists
    app.state.main_loop_task = asyncio.create_task(player.on_startup())

    # Ensure that we connect to the experiment manager before running the app
    async with app.state.experiment_manager_client.connect(connection=api_info):
        # Run the app and wait here until the app is shut down
        yield

    # Cleanup
    logger.info("Shutting down PlayerAPI")

    # If there is a main loop task, cancel it
    if app.state.main_loop_task:
        _ = app.state.main_loop_task.cancel()

    logger.info("Cleaned up player.")
