import base64
from types import TracebackType
from typing import Self

import httpx
import structlog

from gptnt.ktane.actions import KtaneAction
from gptnt.ktane.exceptions import InvalidGameError
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.som.som import SetOfMarksHandler


class KtaneClient:
    """Create a client to interact with the KTANE game."""

    def __init__(
        self, *, client: httpx.AsyncClient, set_of_marks_painter: SetOfMarksHandler | None = None
    ) -> None:
        self.client = client
        self.set_of_marks_painter = set_of_marks_painter

        assert self.client.base_url is not None, "Base URL must be set"

        self._logger = structlog.get_logger().bind(client=self.client.base_url)

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
            self._logger.exception("Game client is not healthy")
            return False

        return True

    async def start_mission(self, specification: KtaneMissionSpec) -> bool:
        """Start a new mission in the environment."""
        response = await self.client.get("/startMission", params=specification.to_query_params())

        try:
            _ = response.raise_for_status()
        except httpx.HTTPError:
            self._logger.exception("Failed to start mission")
            return False
        return True

    async def time_step(self) -> bool:
        """Unpause for 'KtaneMissionSpec.time_step_size' milliseconds.

        Return True if there are no issues with performing this command.
        """
        raise NotImplementedError

    async def send_action(self, action: KtaneAction) -> None:
        """Send an action to the server.

        When we are sending actions to the game, we are always going to be sending a relative
        coordinate of where we are clicking. As a result, this means that using SoM is not
        supported by the game, and any SoM actions must first be converted to relative coordinates.
        """
        endpoint = "/click" if action.is_clicking_action else "/rotation"

        response = await self.client.get(endpoint, params=action.to_query_params())
        try:
            _ = response.raise_for_status()
        except httpx.HTTPError:
            self._logger.exception("Failed to send action")
            return

    async def get_observation(self) -> bytes:
        """Get the current observation from the game as a png."""
        if self.set_of_marks_painter is None:
            return await self._get_screenshot()

        observation_bytes, segm_image_bytes = await self._get_screenshot_with_segm()
        return self.set_of_marks_painter.run(
            observation=observation_bytes, colorful_image=segm_image_bytes
        )

    async def _get_screenshot(self) -> bytes:
        response = await self.client.get("/screenshot")

        try:
            _ = response.raise_for_status()
        except httpx.HTTPError as err:
            raise InvalidGameError("Failed to take screenshot") from err

        base64_data = response.text
        png_data = base64.b64decode(base64_data)
        return png_data

    async def _get_screenshot_with_segm(self) -> tuple[bytes, bytes]:
        raise NotImplementedError
