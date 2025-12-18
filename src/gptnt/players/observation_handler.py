import base64
import binascii
from dataclasses import dataclass
from io import BytesIO
from typing import Annotated

import logfire
import numpy as np
import structlog
from PIL import Image
from pydantic import BaseModel, BeforeValidator, PlainSerializer

from gptnt.common.image_ops import load_observation_from_bytes
from gptnt.ktane.actions import KtaneGameplayInput
from gptnt.ktane.state.bomb import BombState
from gptnt.players.actions import AbsoluteCoordinate, GameInteractionActionType
from gptnt.processors.image_resizer import ImageResizer
from gptnt.processors.set_of_marks import SetOfMarksHandler

logger = structlog.get_logger()


def _parse_base64_to_bytes(data: str | bytes) -> bytes:
    """Decode base64 encoded string to bytes if string."""
    if isinstance(data, bytes):
        return data
    return base64.b64decode(data)


def _serialize_bytes_to_base64(data: bytes) -> str:
    """Serialize bytes to base64 encoded string for JSON."""
    return base64.b64encode(data).decode("utf-8")


ImageBytes = Annotated[
    bytes,
    BeforeValidator(_parse_base64_to_bytes),
    PlainSerializer(_serialize_bytes_to_base64, when_used="json-unless-none"),
]


class Observation(BaseModel):
    """Observation from the game.

    This is a named tuple that contains the observation bytes, the segmentation bytes, and the
    processed image.
    """

    frames: list[ImageBytes]
    segm_mask: ImageBytes | None
    som_image: ImageBytes


@dataclass(kw_only=True)
class ObservationHandler:
    """Handle observations from the game client.

    This deals with set of marks, relative coordinates, and all of that to ensure that it is coming
    and going in the right format.
    """

    image_resizer: ImageResizer | None = None
    set_of_marks_painter: SetOfMarksHandler | None = None

    def reset(self) -> None:
        """Reset the observation handler.

        This is called when the player is reset, and it should reset any internal state.
        """
        if self.set_of_marks_painter:
            self.set_of_marks_painter.reset()
        logger.debug("Observation handler reset, cleared set of marks painter.")

    def handle_new_observation(
        self,
        *,
        frames: list[bytes] | list[str],
        segmentation: str | bytes | None,
        bomb_state: BombState,
        num_frames_to_use: int = 1,
    ) -> Observation:
        """Handle a new observation from the game."""
        # Reset any existing mark-to-coordinate mappings so we don't leak them between observations
        if self.set_of_marks_painter:
            self.set_of_marks_painter.reset()

        with logfire.span("Decoding frames and segmentation"):
            frames = self._decode_frames(frames, num_frames_to_use=num_frames_to_use)
            segmentation = self._decode_segmentation(segmentation)

        # If we are not resizing nor applying SoM, we can just use the last frame
        if self.image_resizer is None and self.set_of_marks_painter is None:
            logger.debug("No image resizer or set of marks painter, using last frame only.")
            return Observation(frames=frames, segm_mask=segmentation, som_image=frames[-1])

        # Make a list of images
        images = [load_observation_from_bytes(frame) for frame in frames]
        # Resize the images if needed
        if self.image_resizer:
            # with logfire.span("Resize images", images=images):
            images = [self.image_resizer.resize_image(image) for image in images]

        # Apply set of marks only on the last image
        last_image = images[-1]
        if self.set_of_marks_painter and segmentation:
            with logfire.span("Applying set of marks on last frame"):
                segm_image = load_observation_from_bytes(segmentation)

                if self.image_resizer:
                    # with logfire.span("Resize segmentation mask", image=segm_image):
                    segm_image = self.image_resizer.resize_image(segm_image)

                last_image = self._apply_set_of_marks(
                    raw_image=last_image, segmentation_image=segm_image, bomb_state=bomb_state
                )
                logger.debug(
                    "Set of marks mapping applied",
                    mark_to_coord_mapping=self.set_of_marks_painter.mark_to_coordinate,
                    bomb_state=bomb_state,
                )

        # Convert the resized / som images back to bytes
        with logfire.span("Saving images back to bytes"):
            som_buffer = BytesIO()
            last_image.save(som_buffer, format="PNG")

            frames = []
            for image in images:
                image_buffer = BytesIO()
                image.save(image_buffer, format="PNG")
                frames.append(image_buffer.getvalue())

        return Observation(frames=frames, segm_mask=segmentation, som_image=som_buffer.getvalue())

    def convert_to_game_action(self, *, action: GameInteractionActionType) -> KtaneGameplayInput:
        """Convert the action to the game action."""
        action_location = action.location
        # Convert from SoM to relative coordinates if needed
        if self.set_of_marks_painter and isinstance(action.location, (int, str)):
            # Convert the SoM to relative coordinates
            logger.info(f"Mark to click is: {action.location}")
            action_location = self.set_of_marks_painter.convert_mark_to_coordinate(
                mark_id=action.location
            )

        if self.image_resizer and isinstance(action_location, AbsoluteCoordinate):
            logger.info(f"Converting absolute coordinate {action_location} to relative.")
            action_location = self.image_resizer.convert_absolute_to_relative(
                coordinate=action_location
            )

        return KtaneGameplayInput.model_validate(
            {**action.model_dump(), "location": action_location}
        )

    def _apply_set_of_marks(
        self, *, raw_image: Image.Image, segmentation_image: Image.Image, bomb_state: BombState
    ) -> Image.Image:
        """Apply the set of marks to the image.

        When we are sending actions to the game, we are always going to be sending a relative
        coordinate of where we are clicking. As a result, this means that using SoM is not
        supported by the game, and any SoM actions must first be converted to relative coordinates.
        """
        if self.set_of_marks_painter is None:
            raise AttributeError("Set of marks painter is not set? Why did this get called.")
        set_of_marks_array = self.set_of_marks_painter.run(
            observation=np.asarray(raw_image),
            colorful_image=np.asarray(segmentation_image),
            zoomed_in_component=bomb_state.zoomed_in_component,
        )
        set_of_marks_image = Image.fromarray(set_of_marks_array.astype(np.uint8), "RGB")
        return set_of_marks_image

    def _decode_segmentation(self, segmentation: str | bytes | None) -> bytes | None:
        """Decode segmentation mask from base64 if needed."""
        if segmentation is None or isinstance(segmentation, bytes):
            return segmentation

        try:
            return base64.b64decode(segmentation)
        except binascii.Error:
            logger.warning(
                "Failed to decode segmentation mask, it might not be base64 encoded? Setting the segmentation to None",
                segmentation=segmentation,
            )
            return None

    def _decode_frames(
        self, frames: list[bytes] | list[str], *, num_frames_to_use: int
    ) -> list[bytes]:
        """Decode frames from base64 if needed."""
        return [
            base64.b64decode(frame) if isinstance(frame, str) else frame
            for frame in frames[-num_frames_to_use:]
        ]
