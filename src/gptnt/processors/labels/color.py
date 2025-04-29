import colorsys

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


def rgb_to_hex(rgb: Color) -> str:
    """Convert an RGB color to a hex string."""
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _rgb_to_hsv(rgb: Color) -> tuple[float, float, float]:
    """Convert an RGB color to HSV."""
    red, green, blue = rgb
    red /= MAX_RGB
    green /= MAX_RGB
    blue /= MAX_RGB
    return colorsys.rgb_to_hsv(red, green, blue)


def _hsv_to_rgb(hsv: tuple[float, float, float]) -> Color:
    """Convert an HSV color to RGB."""
    red, green, blue = colorsys.hsv_to_rgb(*hsv)
    return int(red * MAX_RGB), int(green * MAX_RGB), int(blue * MAX_RGB)


def _boost_vibrancy_hsv(
    hue: float,
    saturation: float,
    value: float,  # noqa: WPS110
    saturation_boost: float = 0.2,
    value_boost: float = 0.1,
) -> tuple[float, float, float]:  # noqa: WPS110
    """Boosts the vibrancy of a color in HSV space.

    - saturation_boost: amount to increase saturation by (default 0.2)
    - value_boost: amount to increase value by (default 0.1)
    Returns modified (hue, saturation, value), clamped to valid ranges.
    """
    new_saturation = min(saturation + saturation_boost, 1.0)
    new_value = min(value + value_boost, 1.0)
    return hue, new_saturation, new_value


def boost_vibrancy(rgb: Color, saturation_boost: float = 0.2, value_boost: float = 0.1) -> Color:
    """Boosts the vibrancy of a color in RGB space.

    - saturation_boost: amount to increase saturation by (default 0.2)
    - value_boost: amount to increase value by (default 0.1)
    Returns modified (r, g, b), clamped to valid ranges.
    """
    hsv = _rgb_to_hsv(rgb)
    boosted_hsv = _boost_vibrancy_hsv(hsv[0], hsv[1], hsv[2], saturation_boost, value_boost)
    return _hsv_to_rgb(boosted_hsv)


def find_text_color(bg_color: Color) -> Color:
    """Find the text color based on the background color.

    The text color is either black or white, depending on the contrast with the background.
    """
    hex_color = rgb_to_hex(bg_color)
    if check_contrast(hex_color, "#FFFFFF"):
        return WHITE
    return BLACK


def _is_white(rgb: Color) -> bool:
    red, green, blue = rgb
    color_minimum = 200
    return red > color_minimum and green > color_minimum and blue > color_minimum


def _is_blue(rgb: Color) -> bool:
    red, green, blue = rgb
    blue_minimum = 150
    other_colors_maximum = 100
    return blue > blue_minimum and red < other_colors_maximum and green < other_colors_maximum


def _is_red(rgb: Color) -> bool:
    red, green, blue = rgb
    red_minimum = 150
    other_colors_maximum = 100
    return red > red_minimum and green < other_colors_maximum and blue < other_colors_maximum


def check_colors(region: RegionProperties, segm_img: RGBArray) -> tuple[bool, bool, bool]:
    """Check for presence of white, blue, and red colors in a region."""
    pixels = np.array([segm_img[y_iter, x_iter] for y_iter, x_iter in region.coords])

    has_white = any(_is_white(rgb) for rgb in pixels)
    has_blue = any(_is_blue(rgb) for rgb in pixels)
    has_red = any(_is_red(rgb) for rgb in pixels)

    return has_white, has_blue, has_red
