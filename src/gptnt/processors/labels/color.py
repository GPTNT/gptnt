import numpy as np

from gptnt.ktane.state.modules import KtaneComponent
from gptnt.processors.labels.types import Color, RegionProperties, RGBArray

ENTIRELY_COLOR_DEPENDENT_MODULES: frozenset[KtaneComponent] = frozenset(
    (KtaneComponent.simon, KtaneComponent.venn, KtaneComponent.wires, KtaneComponent.big_button)
)


def compute_perceived_brightness(*, rgb: Color) -> float:
    """Return perceived brightness of an RGB color (0.0 = black, 1.0 = white)."""
    red, green, blue = rgb

    max_rgb = 255.0

    # Normalize to [0, 1]
    red /= max_rgb
    green /= max_rgb
    blue /= max_rgb

    # Perceived luminance formula (ITU-R BT.709)
    brightness = 0.2126 * red + 0.7152 * green + 0.0722 * blue  # noqa: WPS432

    return brightness


def get_median_colour(region: RegionProperties, segm_img: RGBArray) -> Color:
    """Get the centroid colour of a region in the segmentation image."""
    # Get the centroid coordinates
    pixels = np.array(
        [segm_img[y_iterator, x_iterator] for y_iterator, x_iterator in region.coords]
    )
    median_pixel = np.median(pixels, axis=0)
    color = median_pixel[:3]

    return (int(color[0]), int(color[1]), int(color[2]))
