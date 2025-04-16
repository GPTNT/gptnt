import base64
from types import TracebackType
from typing import Self

import httpx
import structlog

from gptnt.ktane.actions import KtaneAction
from gptnt.ktane.exceptions import InvalidGameError
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.processors.set_of_marks import SetOfMarksHandler


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

    async def reset(self) -> bool:
        """Reset the game to the Setup room."""
        response = await self.client.get("/reset")
        try:
            _ = response.raise_for_status()
        except httpx.HTTPError:
            self._logger.exception("Failed to reset game")
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

    async def advance_time(self, milliseconds: int) -> bool:
        """Move the game forward in time by a given number of milliseconds, then pause it."""
        response_set_step_unit = await self.client.get(
            "/setstepunit", params={"value": milliseconds}
        )
        response_time_step = await self.client.get("/timestep")

        try:
            _ = response_set_step_unit.raise_for_status(), response_time_step.raise_for_status()
        except httpx.HTTPError:
            self._logger.exception("Failed to advance time")
            return False
        return True

    async def stop_time(self) -> bool:
        """Pause the game."""
        response = await self.client.get("/settimescale", params={"value": 0})
        try:
            _ = response.raise_for_status()
        except httpx.HTTPError:
            self._logger.exception("Failed to stop time")
            return False
        return True

    async def resume_time(self) -> bool:
        """Resume the game."""
        response = await self.client.get("/settimescale", params={"value": 1})
        try:
            _ = response.raise_for_status()
        except httpx.HTTPError:
            self._logger.exception("Failed to resume time")
            return False
        return True

    async def send_action(self, action: KtaneAction) -> None:
        """Send an action to the server.

        When we are sending actions to the game, we are always going to be sending a relative
        coordinate of where we are clicking. As a result, this means that using SoM is not
        supported by the game, and any SoM actions must first be converted to relative coordinates.
        """
        endpoint = "action"

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

        observation, colorful_image = await self._get_screenshot_with_segm()
        # If the segmentation is empty, we return the original screenshot.
        if not colorful_image:
            return observation

        return self.set_of_marks_painter.run(
            observation=observation, colorful_image=colorful_image
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

    async def _get_screenshot_with_segm(self) -> tuple[bytes, bytes | None]:
        """Get the current observation from the game as two pngs.

        First is the raw screenshot, second is the segmentation image.
        """
        response = await self.client.get("/observation")

        try:
            _ = response.raise_for_status()
        except httpx.HTTPError as err:
            raise InvalidGameError("Failed to get observation") from err

        response_json = response.json()

        screenshot_png_data = base64.b64decode(response_json.get("screenshot"))

        # When the segmentation is empty, we return an empty byte string.
        segm_png_data = (
            base64.b64decode(response_json.get("segmentation"))
            if response_json["segmentation"]
            else None
        )

        return screenshot_png_data, segm_png_data
