import numpy as np
from color_contrast import check_contrast

from gptnt.core.ktane.state.modules import KtaneComponent
from gptnt.core.processors.labels.types import (  # noqa: WPS235
    BLACK,
    BLUE,
    GREEN,
    IS_LINE_THRESHOLD,
    RED,
    WHITE,
    YELLOW,
    Color,
    RegionProperties,
    RGBArray,
)

ENTIRELY_COLOR_DEPENDENT_MODULES: frozenset[KtaneComponent] = frozenset(
    (KtaneComponent.simon, KtaneComponent.venn, KtaneComponent.wires, KtaneComponent.big_button)
)

MAX_RGB = 255


def get_median_colour(region: RegionProperties, segm_img: RGBArray) -> Color:
    """Get the centroid colour of a region in the segmentation image."""
    # Get the centroid coordinates
    pixels = segm_img[region.coords[:, 0], region.coords[:, 1]]
    median_pixel = np.median(pixels, axis=0)
    color = median_pixel[:3]

    return (int(color[0]), int(color[1]), int(color[2]))


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
    pixels = segm_img[region.coords[:, 0], region.coords[:, 1]]

    has_white = any(_is_white(rgb) for rgb in pixels)
    has_blue = any(_is_blue(rgb) for rgb in pixels)
    has_red = any(_is_red(rgb) for rgb in pixels)

    return has_white, has_blue, has_red


def handle_venn(region: RegionProperties, image: RGBArray) -> tuple[Color, ...]:
    """Check if the region is a venn diagram."""
    has_white, has_blue, has_red = check_colors(region, image)
    color_mapping = {
        (True, True, False): (WHITE, BLUE),
        (True, False, True): (WHITE, RED),
        (False, True, True): (BLUE, RED),
        (True, False, False): (WHITE,),
        (False, True, False): (BLUE,),
    }
    colors = color_mapping.get((has_white, has_blue, has_red), (RED,))
    return colors


def get_region_color(  # noqa: WPS212
    image: RGBArray, segm_image: RGBArray, region: RegionProperties, module: KtaneComponent | None
) -> tuple[Color, ...]:
    """Get the colour of a region based on the module type."""
    # Use image colours for colour dependent modules (but only wire interactables for wire modules)

    if module == KtaneComponent.venn:
        return handle_venn(region, image)

    if module in ENTIRELY_COLOR_DEPENDENT_MODULES or (
        module == KtaneComponent.wire_sequence and region.eccentricity > IS_LINE_THRESHOLD
    ):
        color = get_median_colour(region, image)

        return (color,)

    if module == KtaneComponent.wire_sequence:
        # Set the colors of the wire_sequence buttons so that they do not match one of the wires
        color = get_median_colour(region, segm_image)
        if color == RED:
            return (GREEN,)
        if color == BLUE:
            return (YELLOW,)

    # Otherwise, use segmentation image colour
    return (get_median_colour(region, segm_image),)
