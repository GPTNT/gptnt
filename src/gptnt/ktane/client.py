import base64
from types import TracebackType
from typing import NamedTuple, Self, override

import httpx
import logfire
import structlog
from httpx._exceptions import ConnectError

from gptnt.common.base_client import BaseClient
from gptnt.common.servers import httpx_create_async_client
from gptnt.ktane.actions import KtaneAction
from gptnt.ktane.exceptions import InvalidGameError
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.game import GameState

_logger = structlog.get_logger()


class ObservationFrames(NamedTuple):
    """Frames from the game."""

    frames: list[str]
    segm_mask: str | None


class KtaneClient(BaseClient):
    """Create a client to interact with the KTANE game."""

    def __init__(self, *, url: str | httpx.URL) -> None:
        super().__init__(url=url)
        assert self.client.base_url is not None, "Base URL must be set"

    @override
    def perform_instrumentation(self) -> None:
        _logger.debug("Instrumenting KtaneClient")
        logfire.instrument_httpx(self.client, capture_all=True)

    async def update_url(self, url: str | httpx.URL) -> None:
        """Create a new client with the given base URL."""
        await self.client.aclose()
        self._client = httpx_create_async_client(base_url=url)
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

    async def send_action(self, action: KtaneAction) -> bool | None:
        """Send an action to the server."""
        try:
            response = await self.client.get("/action", params=action.to_query_params())
        except ConnectError:
            _logger.info("Failed to connect.")
            return None

        try:
            _ = response.raise_for_status()
        except httpx.HTTPError as err:
            _logger.exception(f"Failed to send action Reason: {response.text}", exc_info=err)
            return None

        _logger.info("Response from action", response=response.text)

        return True

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
        return state

    async def get_observation_frames(self) -> ObservationFrames:
        """Gets frames and segmentation mask.

        Frames are upto 16 frames and a segmentation mask of the last, most recent frame.
        """
        response = await self.client.get("/buffer")

        try:
            _ = response.raise_for_status()
        except httpx.HTTPError as err:
            _logger.exception(
                f"Failed to get frames. Reason: {response.text}",
                reason=response.text,
                exc_info=err,
            )
            raise InvalidGameError("Failed to get frames") from err

        response_json = response.json()

        frames_png_data = list(response_json.get("frames", []))

        # When the segmentation is empty, we return an empty byte string.
        segm_png_data = (
            response_json.get("segmentation") if response_json["segmentation"] else None
        )

        return ObservationFrames(frames=frames_png_data, segm_mask=segm_png_data)

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
