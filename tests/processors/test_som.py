from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from pytest_cases import fixture, param_fixture

from gptnt.common.image_ops import load_observation_from_bytes
from gptnt.processors.set_of_marks import (
    convert_colorful_segm_to_labeled,
    draw_mask_on_image,
    get_region_properties,
)

segmentation_image_names = param_fixture(
    "segmentation_image_names",
    ["segmentation1.png", "segmentation2.png", "segmentation3.png", "segmentation4.png"],
    scope="session",
)


@fixture(scope="session")
def segmentation_image(fixture_path: Path, segmentation_image_names: str) -> NDArray[np.uint8]:
    """Fixture to provide a segmentation screenshot as a numpy array."""
    path = fixture_path.joinpath(segmentation_image_names)
    assert path.exists()
    return np.asarray(load_observation_from_bytes(path.read_bytes()))


def test_convert_colorful_segm_to_labeled(segmentation_image: NDArray[np.uint8]) -> None:
    labeled_image = convert_colorful_segm_to_labeled(segmentation_image)

    assert labeled_image.shape == segmentation_image.shape[:2]
    assert labeled_image.dtype == np.int8

    # verify unique colors have unique labels
    unique_colors = np.unique(segmentation_image.reshape(-1, 3), axis=0)
    assert len(unique_colors) == len(np.unique(labeled_image))

    # pick a sample color and verify all pixels with that color have same label
    sample_color = segmentation_image[0, 0]
    sample_label = labeled_image[0, 0]
    color_mask = (segmentation_image == sample_color).all(axis=2)
    assert np.all(labeled_image[color_mask] == sample_label)


def test_get_region_properties(segmentation_image: NDArray[np.uint8]) -> None:
    labeled_image = convert_colorful_segm_to_labeled(segmentation_image)
    regions = get_region_properties(labeled_image)

    # basic checks
    assert len(regions) > 0
    assert len(regions) == len(np.unique(labeled_image)) - 1  # exclude background

    for region in regions:
        assert len(region.centroid) == 2


def test_mask_outline_color(segmentation_image: NDArray[np.uint8]) -> None:
    """Test if bounding box is drawn with the correct color."""

    expected_mask_color = (0, 255, 0)  # Green in RGB

    height, width = segmentation_image.shape[:2]
    test_image = np.zeros((height, width, 3), dtype=np.uint8)

    labeled_image = convert_colorful_segm_to_labeled(segmentation_image)
    regions = get_region_properties(labeled_image)

    # Draw masks on the test image
    for region in regions:
        test_image, _ = draw_mask_on_image(
            image=test_image,
            coords=region.coords,
            color=expected_mask_color,
            thickness=2,
            soft_mask_alpha=0.3,
        )

        # TODO: Check if the colour of one of the pixels is correct
