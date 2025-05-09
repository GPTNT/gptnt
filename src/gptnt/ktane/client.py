import base64
from io import BytesIO
from types import TracebackType
from typing import NamedTuple, Self, override

import httpx
import logfire
import numpy as np
import structlog
from PIL import Image

from gptnt.common.base_client import BaseClient
from gptnt.common.image_ops import load_observation_from_bytes
from gptnt.ktane.actions import KtaneAction, KtaneBaseAction
from gptnt.ktane.exceptions import InvalidGameError
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.game import GameState
from gptnt.players.actions import InteractGameLocation
from gptnt.processors.image_resizer import ImageResizer
from gptnt.processors.set_of_marks import SetOfMarksHandler

_logger = structlog.get_logger()


class Observation(NamedTuple):
    """Observation from the game.

    This is a named tuple that contains the observation bytes, the segmentation bytes, and the
    processed image.
    """

    frames: list[bytes]
    segm_mask: bytes
    som_image: bytes


class KtaneClient(BaseClient):
    """Create a client to interact with the KTANE game."""

    def __init__(
        self,
        *,
        url: str | httpx.URL,
        set_of_marks_painter: SetOfMarksHandler | None = None,
        image_resizer: ImageResizer | None = None,
    ) -> None:
        super().__init__(url=url)
        self.set_of_marks_painter = set_of_marks_painter
        self.image_resizer = image_resizer

        self.current_bomb_state: BombState | None = None

        assert self.client.base_url is not None, "Base URL must be set"

    @override
    def perform_instrumentation(self) -> None:
        _logger.debug("Instrumenting KtaneClient")
        logfire.instrument_httpx(self.client, capture_all=True)

    def update_url(self, url: str | httpx.URL) -> None:
        """Create a new client with the given base URL."""
        self._client.base_url = url
        self.perform_instrumentation()

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

    async def gamestate(self) -> GameState:
        """Check if the server is running."""
        response = await self.client.get("/health")
        try:
            _ = response.raise_for_status()
        except httpx.HTTPError as err:
            _logger.exception("Game client is not healthy", exc_info=err)
            return GameState.unknown

        return GameState(response.text)

    async def reset(self) -> bool:
        """Reset the game to the Setup room."""
        response = await self.client.get("/reset")
        try:
            _ = response.raise_for_status()
        except httpx.HTTPError as err:
            _logger.exception("Failed to reset game", exc_info=err)
            return False
        return True

    async def start_mission(self, specification: KtaneMissionSpec) -> bool:
        """Start a new mission in the environment."""
        response = await self.client.get("/startMission", params=specification.to_query_params())

        try:
            _ = response.raise_for_status()
        except httpx.HTTPError as err:
            _logger.exception(f"Failed to start mission Reason: {response.text}", exc_info=err)
            return False
        return True

    async def advance_time(self) -> bool:
        """Do one, in game time step."""
        response_time_step = await self.client.get("/timestep")
        try:
            _ = response_time_step.raise_for_status()
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

    @logfire.instrument("Send action")
    async def send_action(
        self, action: KtaneBaseAction[InteractGameLocation] | KtaneAction
    ) -> bool | None:
        """Send an action to the server.

        When we are sending actions to the game, we are always going to be sending a relative
        coordinate of where we are clicking. As a result, this means that using SoM is not
        supported by the game, and any SoM actions must first be converted to relative coordinates.
        """
        # Convert from SoM to relative coordinates if needed
        if self.set_of_marks_painter and isinstance(action.location, (int, str)):
            # Convert the SoM to relative coordinates
            _logger.info(f"Mark to click is: {action.location}")
            action.location = self.set_of_marks_painter.mark_to_coordinate(mark_id=action.location)

        response = await self.client.get("/action", params=action.to_query_params())
        try:
            _ = response.raise_for_status()
        except httpx.HTTPError as err:
            _logger.exception(f"Failed to send action Reason: {response.text}", exc_info=err)
            return None

        _logger.info("Response from action", response=response.text)

        return True

    @logfire.instrument("Get bomb state")
    async def get_state(self) -> BombState | None:
        """Get the current state of the bomb."""
        try:  # noqa: WPS229
            response = await self.client.get("/state")
            _ = response.raise_for_status()
        except httpx.RequestError as exc:
            _logger.exception(
                f"Failed to request bomb state from {exc.request.url!r}.", exc_info=exc
            )
            return None
        except httpx.HTTPStatusError as err:
            if err.response.text == "Cannot get bomb state in Lights Off state":
                _logger.warning("Cannot get bomb state in Lights Off state")
                return None
            _logger.exception(
                f"Failed to receive bomb state. Reason: {err.response.text}", exc_info=err
            )
            return None

        _logger.debug("Bomb state", bomb_state=response.json())

        state = BombState.model_validate(response.json())
        self.current_bomb_state = state
        return state

    @logfire.instrument("Get observation from environment")
    async def get_observation_frames(self) -> Observation:
        """Gets frames and segmentation mask.

        Frames are upto 12 frames and a segmentation mask of the last, most recent frame.
        """
        frames, segmentation = await self._get_frames_with_segm()
        # If we are not resizing nor applying SoM, we can just use the last frame
        if self.image_resizer is None and self.set_of_marks_painter is None:
            return Observation(
                frames=frames,
                segm_mask=segmentation if segmentation else b"",
                som_image=frames[-1],
            )

        # Make a list of images
        images = [load_observation_from_bytes(frame) for frame in frames]
        # Resize the images if needed
        if self.image_resizer:
            with logfire.span("Resizing images", images=images):
                images = [self.image_resizer.resize_image(image) for image in images]

        # Apply set of marks only on the last image
        last_image = images[-1]
        if self.set_of_marks_painter and segmentation:
            segm_image = load_observation_from_bytes(segmentation)

            if self.image_resizer:
                with logfire.span("Resizing segmentation mask", image=segm_image):
                    segm_image = self.image_resizer.resize_image(segm_image)

            with logfire.span(
                "Perform Set of Marks", observation=last_image, segmentation=segm_image
            ):
                last_image = self._apply_som(
                    raw_image=last_image,
                    segmentation_image=segm_image,
                    set_of_marks_painter=self.set_of_marks_painter,
                )

        # convert the resized / som images back to bytes
        som_buffer = BytesIO()
        last_image.save(som_buffer, format="PNG")

        frames = []
        for image in images:
            image_buffer = BytesIO()
            image.save(image_buffer, format="PNG")
            frames.append(image_buffer.getvalue())

        return Observation(
            frames=frames,
            segm_mask=segmentation if segmentation else b"",
            som_image=som_buffer.getvalue(),
        )

    def _apply_som(
        self,
        raw_image: Image.Image,
        segmentation_image: Image.Image,
        set_of_marks_painter: SetOfMarksHandler,
    ) -> Image.Image:
        som_rgb_array = set_of_marks_painter.run(
            observation=np.asarray(raw_image),
            colorful_image=np.asarray(segmentation_image),
            zoomed_in_component=self.current_bomb_state.zoomed_in_component
            if self.current_bomb_state
            else None,
        )
        return Image.fromarray(som_rgb_array.astype(np.uint8), "RGB")

    async def _get_screenshot(self) -> bytes:
        response = await self.client.get("/screenshot")

        try:
            _ = response.raise_for_status()
        except httpx.HTTPError as err:
            _logger.exception("Failed to get screenshot", exc_info=err)
            raise InvalidGameError("Failed to get screenshot") from err

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

    async def _get_frames_with_segm(self) -> tuple[list[bytes], bytes | None]:
        """Get the most recent frames from the game.

        Including a segmentation mask.
        """
        response = await self.client.get("/buffer")

        try:
            _ = response.raise_for_status()
        except httpx.HTTPError as err:
            _logger.exception(f"Failed to get frames. Reason: {response.text}", exc_info=err)
            raise InvalidGameError("Failed to get frames") from err

        response_json = response.json()

        frames_png_data = [base64.b64decode(frame) for frame in response_json.get("frames", [])]

        # When the segmentation is empty, we return an empty byte string.
        segm_png_data = (
            base64.b64decode(response_json.get("segmentation"))
            if response_json["segmentation"]
            else None
        )

        return frames_png_data, segm_png_data
