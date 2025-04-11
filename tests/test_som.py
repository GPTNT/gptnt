from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from pytest_cases import fixture, param_fixture
from skimage.io import imread

from gptnt.som.som import Bbox, Coordinate, convert_colorful_segm_to_labeled, get_region_properties

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
    return imread(path)


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
        assert isinstance(region.label, (int, np.integer))
        assert isinstance(region.centroid, Coordinate)
        assert len(region.centroid) == 2
        assert isinstance(region.bbox, Bbox)
        assert len(region.bbox) == 4

        # centroid within bbox
        min_row, min_col, max_row, max_col = region.bbox
        x_centroid, y_centroid = region.centroid
        assert min_col <= x_centroid <= max_col
        assert min_row <= y_centroid <= max_row

        # bbox coordinates are valid
        assert min_row < max_row
        assert min_col < max_col
        assert min_row >= 0
        assert min_col >= 0
        assert max_row <= labeled_image.shape[0]
        assert max_col <= labeled_image.shape[1]
