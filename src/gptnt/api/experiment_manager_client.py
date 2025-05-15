from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from structlog import get_logger

from gptnt.api.structures import RoomMetadata
from gptnt.common.base_client import BaseClient
from gptnt.experiments.experiments import ExperimentSpec
from gptnt.players.structures import PlayerMetadata

_logger = get_logger()


class ExperimentManagerClient(BaseClient):
    """API for externally interacting with the ExperimentManagerAPI."""

    @asynccontextmanager
    async def connect(self, *, connection: PlayerMetadata | RoomMetadata) -> AsyncGenerator[None]:
        """Connect to the ExperimentManager.

        Registers this as a valid player for the experiment manager to use for running experiments.
        """
        _logger.debug("Connecting to ExperimentManager", connection=connection)

        if not await self.wait_for_valid_healthcheck():
            raise RuntimeError("ExperimentManager is not healthy.")

        _logger.info("ExperimentManager is healthy.")

        switcher = {PlayerMetadata: self.connect_player, RoomMetadata: self.connect_room}

        endpoint = switcher[type(connection)]
        _ = await endpoint(connection)  # pyright: ignore[reportArgumentType]
        _logger.debug("Connected to ExperimentManager.")
        yield

    async def add_experiment(self, experiment: ExperimentSpec) -> bool:
        """Connect to the ExperimentManager.

        Adds an ExperimentSpec to the ExperimentManager.experiments.
        """
        try:
            _ = (
                await self.client.post(
                    url="/add-experiment", json=experiment.model_dump(mode="json")
                )
            ).raise_for_status()
        except httpx.HTTPError:
            _logger.exception("Failed to connect to ExperimentManager")
            return False
        return True

    async def connect_room(self, connection: RoomMetadata) -> bool:
        """Connect to the ExperimentManager.

        Registers this as a valid room for the experiment manager to use for running experiments.
        """
        try:
            _ = (
                await self.client.post(
                    url="/connect-room", json=connection.model_dump(mode="json")
                )
            ).raise_for_status()
        except httpx.HTTPError:
            _logger.exception("Failed to connect to ExperimentManager")
            return False
        return True

    async def connect_player(self, connection: PlayerMetadata) -> bool:
        """Connect a player to the ExperimentManager.

        Registers this as a valid player for the experiment manager to use for running experiments.
        """
        try:
            _ = (
                await self.client.post(
                    url="/connect-player", json=connection.model_dump(mode="json")
                )
            ).raise_for_status()
        except httpx.HTTPError:
            _logger.exception("Failed to connect to ExperimentManager")
            return False
        return True
