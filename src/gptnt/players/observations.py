import base64
import binascii
from dataclasses import dataclass
from io import BytesIO
from typing import NamedTuple, cast

import numpy as np
import structlog
from PIL import Image

from gptnt.common.image_ops import load_observation_from_bytes
from gptnt.ktane.actions import KtaneAction, KtaneBaseAction, RelativeCoordinate
from gptnt.ktane.state.bomb import BombState
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


@dataclass(kw_only=True)
class ObservationHandler:
    """Handle observations from the game client.

    This deals with set of marks, relative coordinates, and all of that to ensure that it is coming
    and going in the right format.
    """

    image_resizer: ImageResizer | None = None
    set_of_marks_painter: SetOfMarksHandler | None = None

    def handle_new_observtion(  # noqa: WPS231
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

        frames = [
            base64.b64decode(frame) if isinstance(frame, str) else frame
            for frame in frames[-num_frames_to_use:]
        ]
        try:
            segmentation = (
                base64.b64decode(segmentation) if isinstance(segmentation, str) else segmentation
            )
        except binascii.Error:
            _logger.warning(
                "Failed to decode segmentation mask, it might not be base64 encoded.",
                segmentation=segmentation,
            )
            segmentation = None

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
            # with logfire.span("Resize images", images=images):
            images = [self.image_resizer.resize_image(image) for image in images]

        # Apply set of marks only on the last image
        last_image = images[-1]
        if self.set_of_marks_painter and segmentation:
            segm_image = load_observation_from_bytes(segmentation)

            if self.image_resizer:
                # with logfire.span("Resize segmentation mask", image=segm_image):
                segm_image = self.image_resizer.resize_image(segm_image)

            last_image = self._apply_set_of_marks(
                raw_image=last_image, segmentation_image=segm_image, bomb_state=bomb_state
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

    def convert_to_game_action(
        self, *, action: KtaneAction | KtaneBaseAction[InteractGameLocation]
    ) -> KtaneAction:
        """Convert the action to the game action.

        This will convert the action to the game action, which is a list of bytes.

        Note: This will the location in the action object instead of creating a new action object,
        therefore if you are using this, expect it to modify the action in place.
        """
        # Convert from SoM to relative coordinates if needed
        if self.set_of_marks_painter and isinstance(action.location, (int, str)):
            # Convert the SoM to relative coordinates
            _logger.info(f"Mark to click is: {action.location}")
            action.location = self.set_of_marks_painter.mark_to_coordinate(mark_id=action.location)
            assert isinstance(action.location, RelativeCoordinate)

        return cast("KtaneAction", action)

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
