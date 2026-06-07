from pathlib import Path

import pytest
from hypothesis import given, strategies as st
from PIL import Image
from pytest_cases import param_fixture

from gptnt.core.processors.image_resizer import ImageResizer

test_image_names = param_fixture(
    "test_image_names", ["screenshot.png", "screenshot1.png"], scope="session"
)


@pytest.fixture(scope="session")
def test_image(fixture_path: Path, test_image_names: str) -> Image.Image:
    """Fixture to get test images."""
    path = fixture_path.joinpath(test_image_names)
    return Image.open(path)


# Ensure maximum hypothesis is still smaller than smallest image (only downscaling allowed)
@given(
    target_width=st.integers(min_value=1, max_value=1024),
    target_height=st.integers(min_value=1, max_value=1024),
)
def test_resize_targets(target_width: int, target_height: int) -> None:
    resizer = ImageResizer(target_width=target_width, target_height=target_height)
    assert resizer.target_height == target_height
    assert resizer.target_width == target_width


@pytest.mark.parametrize(
    ("target_width", "target_height"), [(100, 100), (200, 150), (400, 300), (640, 480), (799, 599)]
)
def test_resize_images(target_width: int, target_height: int, test_image: Image.Image) -> None:
    resizer = ImageResizer(target_width=target_width, target_height=target_height)
    resized_image = resizer.resize_image(test_image)

    assert resized_image is not None
    assert resized_image.size == (target_width, target_height)
