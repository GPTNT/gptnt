from concurrent import futures
from dataclasses import dataclass
from io import BytesIO

import logfire
import numpy as np
import structlog
from PIL import Image
from pydantic import BaseModel

from gptnt.common.image_ops import PNGBytes
from gptnt.ktane.actions import KtaneGameplayInput, RelativeCoordinate
from gptnt.ktane.client import FrameBuffer
from gptnt.ktane.state.bomb import BombState
from gptnt.players.actions import GameInteractionActionType
from gptnt.players.locations import InteractionLocationMethod, PixelLocation, ScaledLocation
from gptnt.processors.image_resizer import ImageResizer
from gptnt.processors.set_of_marks import SetOfMarksHandler

logger = structlog.get_logger()


def _image_to_png_bytes(img: Image.Image) -> PNGBytes:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class Observation(BaseModel):
    """Observation from the game.

    This is a named tuple that contains the observation bytes, the segmentation bytes, and the
    processed image.
    """

    frames: list[PNGBytes]
    segm_mask: PNGBytes | None
    som_image: PNGBytes


@dataclass(kw_only=True)
class ObservationHandler:
    """Handle observations from the game client.

    This deals with set of marks, relative coordinates, and all of that to ensure that it is coming
    and going in the right format.
    """

    interaction_location_method: InteractionLocationMethod
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
        self, *, frame_buffer: FrameBuffer, bomb_state: BombState, num_frames_to_use: int = 1
    ) -> Observation:
        """Handle a new observation from the game."""
        # Reset any existing mark-to-coordinate mappings so we don't leak them between observations
        if self.set_of_marks_painter:
            self.set_of_marks_painter.reset()

        # If we are not resizing nor applying SoM, we can just use the last frame
        if self.image_resizer is None and self.set_of_marks_painter is None:
            logger.debug("No image resizer or set of marks painter, using last frame only.")
            frames = frame_buffer.extract_frames(
                output="png_bytes", last_n_frames=num_frames_to_use
            )
            return Observation(
                frames=frames,
                segm_mask=frame_buffer.extract_segmentation(output="png_bytes"),
                som_image=frames[-1],
            )

        # Make a list of all the frames (as pillow)
        images = frame_buffer.extract_frames(output="pil_image", last_n_frames=num_frames_to_use)

        # Apply set of marks only on the last image IF we want set of marks
        last_image = images[-1]
        # Decoded once here when SoM runs, then reused for `segm_mask` below so we don't redo
        # the raw-pixels → PIL conversion a second time.
        segmentation: Image.Image | None = None
        if (
            self.set_of_marks_painter
            and frame_buffer.has_segmentation
            and self.interaction_location_method == "set-of-marks"
        ):
            segmentation = frame_buffer.extract_segmentation(output="pil_image")
            assert segmentation is not None
            with logfire.span("Applying set of marks on last frame"):
                last_image = self._apply_set_of_marks(
                    raw_image=last_image, segmentation_image=segmentation, bomb_state=bomb_state
                )
                logger.debug(
                    "Set of marks mapping applied",
                    mark_to_coord_mapping=self.set_of_marks_painter.mark_to_coordinate,
                    bomb_state=bomb_state,
                )

        # Resize the images if needed
        if self.image_resizer:
            images = [self.image_resizer.resize_image(image) for image in images]
            last_image = self.image_resizer.resize_image(last_image)

        # Convert the resized / som images back to bytes in parallel — order is preserved by map.
        # last_image is prepended so som and frames are encoded in one pass.
        with logfire.span("Saving images back to bytes"), futures.ThreadPoolExecutor() as executor:
            all_bytes = list(executor.map(_image_to_png_bytes, [last_image, *images]))

        return Observation(
            frames=all_bytes[1:],
            # Reuse the segmentation PIL already decoded for SoM (same bytes), otherwise decode it.
            segm_mask=(
                _image_to_png_bytes(segmentation)
                if segmentation
                else frame_buffer.extract_segmentation(output="png_bytes")
            ),
            som_image=all_bytes[0],
        )

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

        if self.image_resizer and isinstance(action_location, PixelLocation):
            logger.info(f"Converting absolute coordinate {action_location} to relative.")
            action_location = self.image_resizer.convert_absolute_to_relative(
                coordinate=action_location
            )

        if self.image_resizer and isinstance(action_location, ScaledLocation):
            logger.info(f"Converting normalised coordinate {action_location} to relative.")
            action_location = RelativeCoordinate(
                x_pos=action_location.x / ScaledLocation.upper_bound,
                y_pos=action_location.y / ScaledLocation.upper_bound,
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
        set_of_marks_image = Image.fromarray(set_of_marks_array.astype(np.uint8))
        return set_of_marks_image
