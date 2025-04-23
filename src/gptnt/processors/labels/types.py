from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray
from skimage.measure._regionprops import RegionProperties as _RegionProperties

RegionProperties = _RegionProperties
type Color = tuple[int, int, int]
type RGBArray = NDArray[np.uint8]
type Coordinates = tuple[int, int]

BLACK: Color = (0, 0, 0)
WHITE: Color = (255, 255, 255)
GREEN: Color = (0, 255, 0)
ALPHA_CHANNEL = 4
IS_LINE_THRESHOLD = 0.95


class DrawData(NamedTuple):
    """Data for drawing labels and backgrounds.

    Consists of locations and the regions they correspond to.
    """

    coords: tuple[int, int]
    region: RegionProperties
