from typing import override

import httpx
import logfire
from structlog import get_logger

from gptnt.api.base_client import BaseClient, SupervisedClient
from gptnt.api.structures import RoomMetadata, RoomStage
from gptnt.common.async_ops import healthcheck_interval
from gptnt.ktane.mission_spec import KtaneMissionSpec

_logger = get_logger()


class RoomManagerClient(BaseClient):
    """API for externally interacting with the RoomManager."""

    async def statecheck(self) -> RoomStage:
        """Returns the current state of the RoomManager in its lifecycle."""
        response = await self.client.get(url="/health")
        try:
            _ = response.raise_for_status()
        except httpx.HTTPError:
            _logger.exception("Could not get room state")

        # There are `"` characters in the response, so we need to strip them out for some reason
        return RoomStage(value=response.text.replace('"', ""))

    async def reset_room(self) -> bool:
        """Resets the room, back to a state ready to receive a new experiment config."""
        try:
            _ = (await self.client.post(url="/reset-room")).raise_for_status()
        except httpx.HTTPError as err:
            _logger.exception("Could not reset room", exc_info=err)
            return False
        return True

    async def configure_experiment(self, config: KtaneMissionSpec) -> bool:
        """Configure the experiment for the RoomManager to run."""
        try:
            _ = (
                await self.client.post(
                    url="/configure-experiment", json=config.model_dump(mode="json")
                )
            ).raise_for_status()
        except httpx.HTTPError:
            _logger.exception("Could not configure experiment")
            return False
        return True

    async def start_experiment(self) -> bool:
        """Starts the currently configured experiment."""
        try:
            _ = (await self.client.post(url="/start-experiment")).raise_for_status()
        except httpx.HTTPError:
            _logger.exception("Could not start experiment")
            return False
        return True


class SupervisedRoomManagerClient(SupervisedClient[RoomManagerClient, RoomMetadata]):
    """API for externally interacting with the RoomManager in supervised mode."""

    client_constructor = RoomManagerClient

    @property
    def state(self) -> RoomStage:
        """Returns the current state of the RoomManager in its lifecycle."""
        return self.metadata.state

    @override
    async def supervisor_loop(self) -> None:
        """Returns the supervisor co-routine for this client."""
        while self.is_running:
            try:
                with logfire.suppress_instrumentation():
                    self.metadata.state = await self.client.statecheck()
            except httpx.HTTPError:
                break
            await healthcheck_interval()
        _logger.info("Room died")
        self.is_running = False
        await self.stop()
