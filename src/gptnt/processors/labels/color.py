from typing import cast

import numpy as np
from color_contrast import check_contrast

from gptnt.ktane.state.modules import KtaneComponent
from gptnt.processors.labels.types import BLACK, WHITE, Color, RegionProperties, RGBArray

ENTIRELY_COLOR_DEPENDENT_MODULES: frozenset[KtaneComponent] = frozenset(
    (KtaneComponent.simon, KtaneComponent.venn, KtaneComponent.wires, KtaneComponent.big_button)
)

MAX_RGB = 255


def get_median_colour(region: RegionProperties, segm_img: RGBArray) -> Color:
    """Get the centroid colour of a region in the segmentation image."""
    # Get the centroid coordinates
    pixels = np.array(
        [segm_img[y_iterator, x_iterator] for y_iterator, x_iterator in region.coords]
    )
    median_pixel = np.median(pixels, axis=0)
    color = median_pixel[:3]

    return (int(color[0]), int(color[1]), int(color[2]))


def brighten(rgb: Color, factor: float = 0.2) -> Color:
    """Brighten a color by a factor.

    The factor is how much brighter: 0 = no change, 1 = full white.
    """
    new_rgb = tuple(min(MAX_RGB, int(color + (MAX_RGB - color) * factor)) for color in rgb)  # noqa: WPS221

    return cast("Color", new_rgb)


def rgb_to_hex(rgb: Color) -> str:
    """Convert an RGB color to a hex string."""
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def find_text_color(bg_color: Color) -> Color:
    """Find the text color based on the background color.

    The text color is either black or white, depending on the contrast with the background.
    """
    hex_color = rgb_to_hex(bg_color)
    if check_contrast(hex_color, "#FFFFFF"):
        return WHITE
    return BLACK
