from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from structlog import get_logger

from gptnt.api.base_client import BaseClient
from gptnt.api.structures import PlayerMetadata, RoomMetadata

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
