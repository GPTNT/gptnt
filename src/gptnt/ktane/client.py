from types import TracebackType
from typing import Self

import httpx
import structlog

from gptnt.ktane.structures import KtaneAction, KtaneMissionSpec

logger = structlog.get_logger()


class KtaneClient:
    """Create a client to interact with the KTANE game."""

    def __init__(self, *, client: httpx.AsyncClient) -> None:
        self.client = client

    async def __aenter__(self) -> Self:
        """Open the client."""
        _ = await self.client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        """Close the client."""
        await self.client.__aexit__()

    async def healthcheck(self) -> bool:
        """Check if the server is running."""
        response = await self.client.get("/health")
        try:
            _ = response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Game client is not healthy")
            return False

        return True

    async def start_mission(self, specification: KtaneMissionSpec) -> bool:
        """Start a new mission in the environment."""
        response = await self.client.get("/startMission", params=specification.to_query_params())

        try:
            _ = response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Failed to start mission")
            return False
        return True

    async def time_step(self) -> bool:
        """Unpause for 'KtaneMissionSpec.time_step_size' milliseconds.

        Return True if there are no issues with performing this command.
        """
        raise NotImplementedError

    async def send_action(self, action: KtaneAction) -> None:
        """Send an action to the server."""
        raise NotImplementedError

    async def get_observation(self) -> None:
        """Get the current observation from the game."""
        raise NotImplementedError
