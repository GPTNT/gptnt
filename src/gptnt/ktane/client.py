import base64
from io import BytesIO
from types import TracebackType
from typing import Self, override

import httpx
import logfire
import numpy as np
import structlog
from PIL import Image

from gptnt.common.image_ops import load_observation_from_bytes
from gptnt.common.instrumentation import InstrumentationMixin
from gptnt.ktane.actions import KtaneAction, KtaneBaseAction
from gptnt.ktane.exceptions import InvalidGameError
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.game import GameState
from gptnt.players.actions import InteractGameLocation
from gptnt.processors.image_resizer import ImageResizer
from gptnt.processors.set_of_marks import SetOfMarksHandler

_logger = structlog.get_logger()


class KtaneClient(InstrumentationMixin):
    """Create a client to interact with the KTANE game."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        set_of_marks_painter: SetOfMarksHandler | None = None,
        image_resizer: ImageResizer | None = None,
    ) -> None:
        self.client = client
        self.set_of_marks_painter = set_of_marks_painter
        self.image_resizer = image_resizer

        assert self.client.base_url is not None, "Base URL must be set"

    @override
    def perform_instrumentation(self) -> None:
        _logger.debug("Instrumenting KtaneClient")
        logfire.instrument_httpx(self.client, capture_all=True)

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

    async def healthcheck(self) -> GameState:
        """Check if the server is running."""
        response = await self.client.get("/health")
        try:
            _ = response.raise_for_status()
        except httpx.HTTPError:
            _logger.exception("Game client is not healthy")
            return GameState.unknown

        return GameState(response.text)

    async def reset(self) -> bool:
        """Reset the game to the Setup room."""
        response = await self.client.get("/reset")
        try:
            _ = response.raise_for_status()
        except httpx.HTTPError:
            _logger.exception("Failed to reset game")
            return False
        return True

    async def start_mission(self, specification: KtaneMissionSpec) -> bool:
        """Start a new mission in the environment."""
        response = await self.client.get("/startMission", params=specification.to_query_params())

        try:
            _ = response.raise_for_status()
        except httpx.HTTPError:
            _logger.exception("Failed to start mission")
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
            _logger.exception("Failed to advance time")
            return False
        return True

    async def stop_time(self) -> bool:
        """Pause the game."""
        response = await self.client.get("/settimescale", params={"value": 0})
        try:
            _ = response.raise_for_status()
        except httpx.HTTPError:
            _logger.exception("Failed to stop time")
            return False
        return True

    async def resume_time(self) -> bool:
        """Resume the game."""
        response = await self.client.get("/settimescale", params={"value": 1})
        try:
            _ = response.raise_for_status()
        except httpx.HTTPError:
            _logger.exception("Failed to resume time")
            return False
        return True

    async def send_action(
        self, action: KtaneBaseAction[InteractGameLocation] | KtaneAction
    ) -> BombState | None:
        """Send an action to the server.

        When we are sending actions to the game, we are always going to be sending a relative
        coordinate of where we are clicking. As a result, this means that using SoM is not
        supported by the game, and any SoM actions must first be converted to relative coordinates.
        """
        # Convert from SoM to relative coordinates if needed
        if self.set_of_marks_painter and isinstance(action.location, int):
            # Convert the SoM to relative coordinates
            action.location = self.set_of_marks_painter.mark_to_coordinate(mark_id=action.location)

        response = await self.client.get("/action", params=action.to_query_params())
        try:
            _ = response.raise_for_status()
        except httpx.HTTPError:
            _logger.exception("Failed to send action")
            return None

        return BombState.model_validate_json(response.text)

    async def get_state(self) -> BombState | None:
        """Get the current state of the bomb."""
        response = await self.client.get("/state")
        try:
            _ = response.raise_for_status()
        except httpx.HTTPError:
            _logger.exception("Failed to get bomb state")
            return None
        return BombState.model_validate_json(response.text)

    @logfire.instrument("Get observation from environment")
    async def get_observation(self) -> bytes:  # noqa: WPS615
        """Get the current observation from the game as a png."""
        # If we are not resizing or using SoM, we can just get the screenshot as bytes and pass it
        # on as is
        if self.set_of_marks_painter is None and self.image_resizer is None:
            return await self._get_screenshot()

        # Incase we are going to be using SoM, we need to get the screenshot and the segmentation
        observation_bytes, segmentation_bytes = await self._get_screenshot_with_segm()
        observation = load_observation_from_bytes(observation_bytes)

        # If we are resizing the image, we need to resize it before passing it on
        if self.image_resizer:
            with logfire.span("Resizing image", image=observation):
                observation = self.image_resizer.resize_image(observation)

        if self.set_of_marks_painter and segmentation_bytes:
            segmentation = load_observation_from_bytes(segmentation_bytes)

            # If we are using SoM, we also need to resize the segmentation image
            if self.image_resizer:
                with logfire.span("Resizing image", image=segmentation):
                    segmentation = self.image_resizer.resize_image(segmentation)

            # Apply SoM onto the image
            with logfire.span(
                "Perform Set of Marks", observation=observation, segmentation=segmentation
            ):
                observation = self.set_of_marks_painter.run(
                    observation=np.asarray(observation), colorful_image=np.asarray(segmentation)
                )

            # convert back to pillow image
            observation = Image.fromarray(observation.astype(np.uint8), "RGB")

        buffer = BytesIO()
        observation.save(buffer, format="PNG")
        return buffer.getvalue()

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
