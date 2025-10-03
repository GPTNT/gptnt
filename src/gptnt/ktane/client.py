from dataclasses import dataclass
from typing import Annotated

import httpx
import logfire
import structlog
from pydantic import AfterValidator, BaseModel, Field

from gptnt.common.base_client import BaseClient
from gptnt.ktane.actions import KtaneAction
from gptnt.ktane.game_settings import KtaneSettings
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.game import GameState

_logger = structlog.get_logger()


def add_failure_reason_from_response(response: httpx.Response) -> None:
    """Add a failure reason to the response if it exists."""
    if response.is_error:
        response.headers["X-Reason"] = response.text


class RawObservationFrames(BaseModel):
    """Frames from the game.

    We keep everything as base64 strings and also note that since they come from the JSON, they
    don't need to be url-safe and I don't believe that they are.
    """

    frames: Annotated[list[str], Field(default_factory=list)]
    segmentation: Annotated[
        str | None, AfterValidator(lambda image: image if bool(image) else None)
    ] = None


@dataclass(kw_only=True)
class KtaneClient(BaseClient):
    """Client that interacts with the KTANE game itself."""

    async def update_url(self, url: str | httpx.URL) -> None:
        """Create a new client with the given base URL."""
        await self.client.aclose()
        self.recreate_client(url=url)

    @property
    def default_game_speed(self) -> int:
        """Get the game speed."""
        return KtaneSettings().game_speed

    async def get_game_state(self) -> GameState:
        """Get the current state that the game is in."""
        response = await self.client.get("/health")
        if response.is_error:
            _logger.error("Game client is not healthy", request=response.request)
            return GameState.unknown
        return GameState(response.text)

    async def go_to_main_menu(self) -> bool:
        """Reset the game to the Setup room/main menu."""
        response = await self.client.get("/reset")
        return response.is_success

    @logfire.instrument("Start mission")
    async def start_mission(self, specification: KtaneMissionSpec) -> bool:
        """Start a new mission in the environment."""
        response = await self.client.get(
            "/startMission",
            params=specification.model_copy(
                update={"time_scale": self.default_game_speed}
            ).to_query_params(),
        )
        response = response.raise_for_status()
        return response.is_success

    async def advance_time(self) -> bool:
        """Advance the time by the `time_step_size`, and then pause.

        Defaulted to 3000ms.
        """
        response = await self.client.get("/timestep")
        response = response.raise_for_status()
        return response.is_success

    async def set_game_speed(self, *, speed: float | None = None) -> bool:
        """Set the game speed.

        If set to None, we use the default (from the settings).
        """
        if speed is None:
            speed = self.default_game_speed
        response = await self.client.get("/settimescale", params={"value": speed})
        response = response.raise_for_status()
        return response.is_success

    async def stop_time(self) -> bool:
        """Pause the game."""
        return await self.set_game_speed(speed=0)

    async def resume_time(self) -> bool:
        """Resume the game."""
        return await self.set_game_speed()

    async def send_action(self, action: KtaneAction) -> bool:
        """Perform an action in the game."""
        response = await self.client.get("/action", params=action.to_query_params())
        response = response.raise_for_status()
        return response.is_success

    async def get_bomb_state(self) -> BombState:
        """Get the current state of the bomb."""
        response = await self.client.get("/state")
        response = response.raise_for_status()

        _logger.debug("Received bomb state", bomb_state=response.json())
        state = BombState.model_validate(response.json())
        return state

    async def get_observation_frames(self) -> RawObservationFrames:
        """Gets frames and segmentation mask.

        Frames are upto 16 frames and a segmentation mask of the last, most recent frame.
        """
        # Because this can take a while, it can mean that the game has ended in the middle,
        # causing something like a connecttimeout when the game is dead (due to the post-game
        # scenario already happened) or another reason, so we need to catch it and handle it. This
        # is coming through as a connecttimeout
        response = await self.client.get("/buffer")
        _ = response.raise_for_status()

        # Get the json from the thing. We keep everything as base64 encoded strings
        observation_frames = RawObservationFrames.model_validate(response.json())
        return observation_frames

    async def detonate_bomb(self) -> bool:
        """Detonate the bomb."""
        response = await self.client.get("/detonate")
        response = response.raise_for_status()
        return response.is_success

    async def solve_bomb(self) -> bool:
        """Solve the bomb.

        Might take a while of the bomb contains Memory module.
        """
        response = await self.client.get("/solve")
        response = response.raise_for_status()
        return response.is_success
