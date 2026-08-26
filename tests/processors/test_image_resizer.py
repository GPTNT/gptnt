from pathlib import Path

import pytest
from PIL import Image
from pytest_cases import param_fixture

from gptnt.processors.image_resizer import ImageResizer

test_image_names = param_fixture(
    "test_image_names", ["screenshot.png", "screenshot1.png"], scope="session"
)


@pytest.fixture(scope="session")
def test_image(fixture_path: Path, test_image_names: str) -> Image.Image:
    """Fixture to get test images."""
    path = fixture_path.joinpath(test_image_names)
    return Image.open(path)


@pytest.mark.parametrize(
    ("target_width", "target_height"), [(100, 100), (200, 150), (400, 300), (640, 480), (799, 599)]
)
def test_resize_images(target_width: int, target_height: int, test_image: Image.Image) -> None:
    resizer = ImageResizer(target_width=target_width, target_height=target_height)
    resized_image = resizer.resize_image(test_image)

    assert resized_image.size == (target_width, target_height)
