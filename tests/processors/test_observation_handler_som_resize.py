from pathlib import Path

import numpy as np
from pytest_cases import fixture, param_fixture

from gptnt.common.image_ops import load_observation_from_bytes
from gptnt.ktane.actions import RelativeCoordinate
from gptnt.ktane.client import FrameBuffer
from gptnt.ktane.state.bomb import BombState
from gptnt.players.actions import InteractGameAction, SetOfMarksLocation
from gptnt.players.observation_handler import ObservationHandler
from gptnt.processors.image_resizer import ImageResizer
from gptnt.processors.labels.drawing import AnnotationBackgroundParams, AnnotationTextParams
from gptnt.processors.set_of_marks import MaskDrawingParams, SetOfMarksHandler

image_dimensions = param_fixture(
    "image_dimensions",
    [
        (448, 448),  # Square resize (different aspect ratio)
        (512, 384),  # Same as original (maintains aspect ratio)
    ],
    ids=["square_resize", "same_aspect_resize"],
)


@fixture
def som_handler() -> SetOfMarksHandler:
    """Create a Set of Marks handler with alphabet marks."""
    annotation_text_params = AnnotationTextParams(
        font=0, font_scale=0.5, thickness=1, space_between_boxes=2
    )
    annotation_background_params = AnnotationBackgroundParams(padding=0, alpha=0.5)
    mask_drawing_params = MaskDrawingParams(
        mask_thickness=1, soft_mask_alpha=0.5, bw_outside_mask=False
    )
    return SetOfMarksHandler(
        annotation_background_params=annotation_background_params,
        annotation_text_params=annotation_text_params,
        mask_drawing_params=mask_drawing_params,
        mark_type="alphabet",
    )


@fixture
def image_resizer(image_dimensions: tuple[int, int]) -> ImageResizer:
    return ImageResizer(target_width=image_dimensions[0], target_height=image_dimensions[1])


@fixture
def observation_handler(
    som_handler: SetOfMarksHandler, image_resizer: ImageResizer
) -> ObservationHandler:
    """Create an observation handler with both SoM and image resizer enabled."""
    return ObservationHandler(
        interaction_location_method="set-of-marks",
        set_of_marks_painter=som_handler,
        image_resizer=image_resizer,
    )


@fixture
def wires_screen_image(fixture_path: Path) -> bytes:
    """Load the wires-6 screen image from the SoM dataset (512x384)."""
    image_path = fixture_path.joinpath("som_dataset/wires-6-screen.png")
    assert image_path.exists(), f"Wires screen image not found at {image_path}"
    return image_path.read_bytes()


@fixture
def wires_segmentation_image(fixture_path: Path) -> bytes:
    """Load the wires-6 segmentation image from the SoM dataset (512x384)."""
    image_path = fixture_path.joinpath("som_dataset/wires-6-segm.png")
    assert image_path.exists(), f"Wires segmentation image not found at {image_path}"
    return image_path.read_bytes()


@fixture
def wires_frame_buffer(wires_screen_image: bytes, wires_segmentation_image: bytes) -> FrameBuffer:
    """Create a FrameBuffer for the wires-6 observation."""
    screen_image = load_observation_from_bytes(wires_screen_image)
    segm_image = load_observation_from_bytes(wires_segmentation_image)
    return FrameBuffer.from_pil_images(frames=[screen_image], segmentation_mask=segm_image)


@fixture
def minimal_bomb_state() -> BombState:
    """Create a minimal bomb state for testing."""
    return BombState.model_validate(
        {
            "seed": 12345,
            "maxStrikes": 3,
            "strikes": None,
            "isDetonated": False,
            "isSolved": False,
            "isLightOn": True,
            "bombSide": "front",
            "timerModule": {
                "name": "Timer",
                "onFront": True,
                "index": 0,
                "seconds_remaining": 300.0,
            },
            "widgets": [],
            "modules": [],
            "zoomed_in_component": "wires",
        }
    )


def test_som_coordinates_preserved_after_resize(
    observation_handler: ObservationHandler,
    wires_screen_image: bytes,
    wires_segmentation_image: bytes,
    wires_frame_buffer: FrameBuffer,
    minimal_bomb_state: BombState,
) -> None:
    """Test that SoM mark-to-coordinate mapping uses original image dimensions (512x384).

    This test verifies that:
    1. SoM is applied to the original 512x384 image
    2. Mark-to-coordinate mapping is computed using original dimensions
    3. The image is then resized to 448x448
    4. Coordinates still reference the original 512x384 dimensions, not 448x448

    CRITICAL: This test will FAIL if SoM is applied AFTER resizing because:
    - Coordinates would be computed relative to 448x448 instead of 512x384
    - The coordinate values would differ from the expected original-image coordinates
    """
    original_image = load_observation_from_bytes(wires_screen_image)

    # STEP 1: Get reference coordinates by applying SoM to ORIGINAL 512x384 image
    # This gives us the expected coordinates if SoM is applied BEFORE resize
    som_handler_ref = observation_handler.set_of_marks_painter
    assert som_handler_ref is not None

    segm_image_original = load_observation_from_bytes(wires_segmentation_image)
    _ = som_handler_ref.run(
        observation=np.asarray(original_image),
        colorful_image=np.asarray(segm_image_original),
        zoomed_in_component=minimal_bomb_state.zoomed_in_component,
    )
    expected_coordinates = dict(som_handler_ref.mark_to_coordinate)

    # Reset for the actual test
    som_handler_ref.reset()

    # STEP 2: Handle the observation through the full pipeline
    # This should apply SoM BEFORE resizing
    _ = observation_handler.handle_new_observation(
        frame_buffer=wires_frame_buffer, bomb_state=minimal_bomb_state, num_frames_to_use=1
    )

    # Verify SoM was applied and marks were created
    som_handler = observation_handler.set_of_marks_painter
    assert som_handler is not None
    assert len(som_handler.mark_to_coordinate) > 0, "No marks were created"

    # Get the first mark and its coordinate
    first_mark = next(iter(som_handler.mark_to_coordinate.keys()))
    coordinate = som_handler.mark_to_coordinate[first_mark]

    # Verify coordinate is a RelativeCoordinate in [0, 1] range
    assert isinstance(coordinate, RelativeCoordinate)
    assert 0 <= coordinate.x_pos <= 1, f"X coordinate {coordinate.x_pos} out of [0, 1] range"
    assert 0 <= coordinate.y_pos <= 1, f"Y coordinate {coordinate.y_pos} out of [0, 1] range"

    # Convert relative coordinate back to pixel coordinates using ORIGINAL dimensions
    original_pixel_x = coordinate.x_pos * original_image.width
    original_pixel_y = coordinate.y_pos * original_image.height

    # Verify the pixel coordinates are within the original image bounds
    # Pixels are 0-indexed, so valid range is [0, width) and [0, height)
    assert 0 <= original_pixel_x < 512, (
        f"Original pixel X {original_pixel_x} out of bounds [0, 512)"
    )
    assert 0 <= original_pixel_y < 384, (
        f"Original pixel Y {original_pixel_y} out of bounds [0, 384)"
    )

    # If we incorrectly used the resized dimensions (448x448), the coordinates would map differently
    # Let's verify that the coordinate doesn't make sense for 448x448 when the aspect ratio differs
    # For the original 512x384 image, the aspect ratio is 4:3
    # After resize to 448x448 (1:1), if marks were computed post-resize, coordinates would be different

    # The key test: verify that convert_som_location_to_coordinate returns the same coordinate
    # that was stored in mark_to_coordinate (which was computed on original dimensions)
    converted_coordinate = som_handler.convert_mark_to_coordinate(mark_id=first_mark)
    assert converted_coordinate == coordinate, (
        f"Converted coordinate {converted_coordinate} doesn't match stored coordinate {coordinate}"
    )

    # CRITICAL TEST: Verify coordinates match the reference coordinates from original 512x384 image
    # If SoM was applied AFTER resizing to 448x448, these values would be different!
    expected_coord = expected_coordinates[first_mark]
    tolerance = 0.001  # Allow tiny floating point differences

    assert abs(coordinate.x_pos - expected_coord.x_pos) < tolerance, (
        f"X coordinate mismatch for mark '{first_mark}'!\n"
        f"  Got:      {coordinate.x_pos:.6f}\n"
        f"  Expected: {expected_coord.x_pos:.6f} (from original 512x384 image)\n"
        f"  Difference: {abs(coordinate.x_pos - expected_coord.x_pos):.6f}\n"
        f"This suggests SoM was applied AFTER resize to 448x448 instead of BEFORE!"
    )
    assert abs(coordinate.y_pos - expected_coord.y_pos) < tolerance, (
        f"Y coordinate mismatch for mark '{first_mark}'!\n"
        f"  Got:      {coordinate.y_pos:.6f}\n"
        f"  Expected: {expected_coord.y_pos:.6f} (from original 512x384 image)\n"
        f"  Difference: {abs(coordinate.y_pos - expected_coord.y_pos):.6f}\n"
        f"This suggests SoM was applied AFTER resize to 448x448 instead of BEFORE!"
    )


def test_som_mark_to_coordinate_conversion_through_observation_handler(
    observation_handler: ObservationHandler,
    wires_frame_buffer: FrameBuffer,
    minimal_bomb_state: BombState,
) -> None:
    """Test the full flow from observation handling to coordinate conversion.

    This test verifies the end-to-end flow:
    1. Handle observation with SoM and resize
    2. Extract marks from the SoM handler
    3. Convert marks back to coordinates via the SoM handler
    4. Verify coordinates are relative to original dimensions
    """
    # Handle the observation
    _ = observation_handler.handle_new_observation(
        frame_buffer=wires_frame_buffer, bomb_state=minimal_bomb_state, num_frames_to_use=1
    )

    som_handler = observation_handler.set_of_marks_painter
    assert som_handler is not None
    assert len(som_handler.mark_to_coordinate) > 0, "No marks were created"

    # Test conversion for each mark
    for mark, expected_coordinate in som_handler.mark_to_coordinate.items():
        # Convert mark to coordinate
        converted_coordinate = som_handler.convert_mark_to_coordinate(mark_id=mark)

        # Verify the coordinate matches what was stored
        assert converted_coordinate == expected_coordinate, (
            f"Mark '{mark}': converted coordinate {converted_coordinate} != "
            f"expected coordinate {expected_coordinate}"
        )

        # Verify coordinate is in valid range
        assert 0 <= converted_coordinate.x_pos <= 1
        assert 0 <= converted_coordinate.y_pos <= 1

        # Verify the coordinate can be mapped back to original image pixels
        # Pixels are 0-indexed, so valid range is [0, width) and [0, height)
        pixel_x = converted_coordinate.x_pos * 512
        pixel_y = converted_coordinate.y_pos * 384
        assert 0 <= pixel_x < 512
        assert 0 <= pixel_y < 384


def test_som_click_action_converts_to_original_coordinates(
    observation_handler: ObservationHandler,
    wires_frame_buffer: FrameBuffer,
    minimal_bomb_state: BombState,
) -> None:
    """Test that click actions with SoM marks convert to coordinates relative to original image.

    This test verifies the integration between ObservationHandler and action conversion:
    1. Handle observation with SoM applied before resize
    2. Create a click action using a SoM mark
    3. Convert the action to game coordinates via convert_to_game_action
    4. Verify the resulting coordinate is relative to the original 512x384 dimensions
    """
    # Handle the observation to create marks
    _ = observation_handler.handle_new_observation(
        frame_buffer=wires_frame_buffer, bomb_state=minimal_bomb_state, num_frames_to_use=1
    )

    som_handler = observation_handler.set_of_marks_painter
    assert som_handler is not None
    assert len(som_handler.mark_to_coordinate) > 0, "No marks were created"

    # Get the first mark
    first_mark = next(iter(som_handler.mark_to_coordinate.keys()))
    expected_coordinate = som_handler.mark_to_coordinate[first_mark]

    # Create a click action using the SoM mark
    click_action = InteractGameAction[SetOfMarksLocation](action="click", location=first_mark)

    # Convert the action to game coordinates
    game_action = observation_handler.convert_to_game_action(action=click_action)

    # Verify the game action has a RelativeCoordinate
    assert isinstance(game_action.location, RelativeCoordinate)

    # Verify it matches the expected coordinate from the mark_to_coordinate mapping
    assert game_action.location.x_pos == expected_coordinate.x_pos
    assert game_action.location.y_pos == expected_coordinate.y_pos

    # Verify the coordinate is in valid range
    assert 0 <= game_action.location.x_pos <= 1
    assert 0 <= game_action.location.y_pos <= 1

    # Convert to pixel coordinates using ORIGINAL dimensions
    # Pixels are 0-indexed, so valid range is [0, width) and [0, height)
    pixel_x = game_action.location.x_pos * 512
    pixel_y = game_action.location.y_pos * 384
    assert 0 <= pixel_x < 512, f"Pixel X {pixel_x} out of bounds [0, 512)"
    assert 0 <= pixel_y < 384, f"Pixel Y {pixel_y} out of bounds [0, 384)"
