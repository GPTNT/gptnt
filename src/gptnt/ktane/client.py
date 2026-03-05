import io
import struct
from concurrent import futures
from dataclasses import dataclass
from typing import Annotated, Literal, Self, overload

import httpx
import logfire
import structlog
from PIL import Image
from pydantic import RootModel

from gptnt.common.base_client import ManagedHttpClient
from gptnt.common.image_ops import PNGBytes, parse_base64_to_bytes, serialize_bytes_to_base64
from gptnt.ktane.actions import KtaneGameplayInput
from gptnt.ktane.game_settings import KtaneSettings
from gptnt.ktane.mission_spec import KtaneMissionConfig
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.game import GameState

_logger = structlog.get_logger()


INT_BYTE_SIZE = 4
BOOL_BYTE_SIZE = 1
HEADER_BYTE_SIZE = BOOL_BYTE_SIZE + 3 * INT_BYTE_SIZE
COLOR_CHANNELS = 3


PNGPixelBytes = Annotated[bytes, parse_base64_to_bytes, serialize_bytes_to_base64]
"""Pixel data for a PNG image.

This is the raw pixel data, not the PNG file bytes.
"""


class FrameBuffer(RootModel[PNGPixelBytes]):
    """Raw frame buffer from KTANE.

    The raw bytes are in the format of:
    1 byte bool: has_segmentation
    4 bytes int: frame count up to 16
    4 bytes int: height
    4 bytes int: width
    Followed by frame count * (width * height * 3) bytes of RGB24 data (3 bytes per pixel)
    If has_segmentation is true, the last image is the segmentation mask
    """

    @classmethod
    def from_pil_images(
        cls, frames: list[Image.Image], segmentation_mask: Image.Image | None = None
    ) -> Self:
        """Create a FrameBuffer from a list of PIL images and an optional segmentation mask.

        This is primarily for testing purposes, as in practice we will be receiving the raw bytes
        from the game.
        """
        all_frames = [*frames, segmentation_mask] if segmentation_mask else frames

        # Store with Unity's flipped Y-axis, matching what FrameBuffer expects
        pixel_data = b"".join(
            frame.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes() for frame in all_frames
        )

        # Pack header: bool(1) + frame_count(4) + height(4) + width(4) = 13 bytes
        width, height = all_frames[0].size
        frame_count = len(all_frames)
        header = struct.pack(
            "<Biii", int(segmentation_mask is not None), frame_count, height, width
        )

        return cls(header + pixel_data)

    @property
    def has_segmentation(self) -> bool:
        """Quickly check if we have a segmentation mask in the buffer."""
        return self.root[0] == 1

    @property
    def frame_count(self) -> int:
        """Get the number of frames in the buffer."""
        return struct.unpack_from("<i", self.root, BOOL_BYTE_SIZE)[0]

    @property
    def frame_height(self) -> int:
        """Get the height of a frame."""
        return struct.unpack_from("<i", self.root, BOOL_BYTE_SIZE + INT_BYTE_SIZE)[0]

    @property
    def frame_width(self) -> int:
        """Get the width of a frame."""
        return struct.unpack_from("<i", self.root, BOOL_BYTE_SIZE + 2 * INT_BYTE_SIZE)[0]

    @overload
    def extract_frames(
        self, *, output: Literal["pil_image"], last_n_frames: int | None = None
    ) -> list[Image.Image]: ...

    @overload
    def extract_frames(
        self, *, output: Literal["png_bytes"], last_n_frames: int | None = None
    ) -> list[PNGBytes]: ...

    def extract_frames(
        self, *, output: Literal["pil_image", "png_bytes"], last_n_frames: int | None = None
    ) -> list[PNGBytes] | list[Image.Image]:
        """Convert the last n frames from the buffer to the desired output format."""
        frame_pixel_data = self._get_frames_pixel_data(last_n_frames=last_n_frames)
        frame_size = self.frame_width * self.frame_height * COLOR_CHANNELS
        chunks = [
            frame_pixel_data[chunk_start : chunk_start + frame_size]
            for chunk_start in range(0, len(frame_pixel_data), frame_size)
        ]

        with futures.ThreadPoolExecutor() as executor:
            images = list(executor.map(self._convert_pixels_to_image, chunks))

            if output == "png_bytes":
                images = list(executor.map(self._image_to_png_bytes, images))

        return images

    @overload
    def extract_segmentation(self, *, output: Literal["pil_image"]) -> Image.Image | None: ...

    @overload
    def extract_segmentation(self, *, output: Literal["png_bytes"]) -> PNGBytes | None: ...

    def extract_segmentation(
        self, *, output: Literal["pil_image", "png_bytes"]
    ) -> PNGBytes | Image.Image | None:
        """Extract the segmentation mask from the buffer, if it exists."""
        if not self.has_segmentation:
            return None
        segmentation_size = self.frame_width * self.frame_height * COLOR_CHANNELS
        segmentation_pixel_data = self.root[-segmentation_size:]
        segmentation_image = self._convert_pixels_to_image(segmentation_pixel_data)
        if output == "png_bytes":
            segmentation_image = self._image_to_png_bytes(segmentation_image)
        return segmentation_image

    def _get_frames_pixel_data(self, last_n_frames: int | None = None) -> bytes:
        frame_size = self.frame_width * self.frame_height * COLOR_CHANNELS
        count = self.frame_count if last_n_frames is None else min(self.frame_count, last_n_frames)

        end = HEADER_BYTE_SIZE + self.frame_count * frame_size
        start = end - count * frame_size
        return self.root[start:end]

    def _convert_pixels_to_image(self, frame_data: bytes) -> Image.Image:
        img = Image.frombytes("RGB", (self.frame_width, self.frame_height), frame_data)
        return img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)  # Unity y axis is flipped

    def _image_to_png_bytes(self, img: Image.Image) -> PNGBytes:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


@dataclass(kw_only=True)
class KtaneClient(ManagedHttpClient):
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
    async def start_mission(self, config: KtaneMissionConfig) -> bool:
        """Start a new mission in the environment."""
        response = await self.client.get(
            "/startMission",
            params=config.model_copy(
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

    async def send_action(self, action: KtaneGameplayInput) -> bool:
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

    async def get_observation_frames(self) -> FrameBuffer:
        """Gets frames and segmentation mask.

        Frames are upto 16 frames and a segmentation mask of the last, most recent frame.
        """
        # Because this can take a while, it can mean that the game has ended in the middle,
        # causing something like a connecttimeout when the game is dead (due to the post-game
        # scenario already happened) or another reason, so we need to catch it and handle it. This
        # is coming through as a connecttimeout
        response = await self.client.get("/buffer", headers={"Connection": "close"})
        _ = response.raise_for_status()

        observations = FrameBuffer(response.read())
        return observations

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
