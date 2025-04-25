from pathlib import Path

import cv2
import numpy as np
import polars as pl
import streamlit as st

from gptnt.common.image_ops import load_observation_from_bytes
from gptnt.ktane.state.modules import KtaneComponent
from gptnt.processors.set_of_marks import (
    COMPONENT_WRITE_LABEL_MAPPER,
    SetOfMarksHandler,
    convert_colorful_segm_to_labeled,
    get_region_properties,
)


def regionprops_to_streamlit_table(regions):
    # Default properties if none specified
    properties = [
        "label",
        "area",
        "perimeter",
        # "centroid",
        # "bbox",
        "eccentricity",
        "orientation",
        "solidity",
        "feret_diameter_max",
    ]

    # Initialize data dictionary
    data = {prop: [] for prop in properties}

    # Fill data from each region
    for region in regions:
        for prop in properties:
            if hasattr(region, prop):
                value = getattr(region, prop)

                # Format tuple values (like centroid, bbox) for better display
                if isinstance(value, tuple):
                    value = str(value)

                data[prop].append(value)
            else:
                data[prop].append(None)

    # Create DataFrame
    df = pl.from_dict(data).with_columns(
        pl.col("orientation").mul(180).truediv(3.14).alias("degrees").abs().floordiv(15).mul(15),
        pl.col("eccentricity").ge(0.95).alias("is_line"),
    )

    # Display in Streamlit
    st.dataframe(df, hide_index=True)

    return df


def place_labels_on_convex_hull(image, regions):
    """Places labels at the furthest point of each region's convex hull."""
    result = image.copy()

    for i, region in enumerate(regions):
        # Get the convex hull coordinates
        hull_coords = region.convex_image
        minr, minc, maxr, maxc = region.bbox
        cy, cx = region.centroid

        # Find the point on the hull that's farthest from the centroid
        max_dist = 0
        outer_y, outer_x = 0, 0

        # Get coordinates of hull points
        hull_points = np.where(hull_coords)

        for y, x in zip(hull_points[0], hull_points[1], strict=False):
            # Convert from region coordinates to image coordinates
            img_y = y + minr
            img_x = x + minc

            dist = np.sqrt((img_y - cy) ** 2 + (img_x - cx) ** 2)
            if dist > max_dist:
                max_dist = dist
                outer_y = img_y
                outer_x = img_x

        # Calculate label position with offset outside the boundary
        direction_y = outer_y - cy
        direction_x = outer_x - cx
        norm = np.sqrt(direction_y**2 + direction_x**2)

        if norm > 0:
            offset = 15  # pixels
            label_y = int(outer_y + (direction_y / norm) * offset)
            label_x = int(outer_x + (direction_x / norm) * offset)

            # Ensure coordinates are within image bounds
            label_y = max(0, min(image.shape[0] - 1, label_y))
            label_x = max(0, min(image.shape[1] - 1, label_x))

            # Add label text
            cv2.putText(
                result,
                f"{i + 1}",
                (label_x, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
            )

    return result


def vectorized_label_placement(image, regions):
    """Uses vectorized operations to efficiently find extreme boundary points and place labels
    optimally."""
    result = image.copy()

    # Get image center
    img_h, img_w = image.shape[0:2]
    img_center_y, img_center_x = img_h // 2, img_w // 2

    # Text properties
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.7
    thickness = 2
    text_color = (255, 255, 255)
    padding = 10  # Padding from object boundary

    for i, region in enumerate(regions):
        # Get region centroid
        cy, cx = region.centroid

        # Get region coordinates
        coords = region.coords  # (row, col) pairs

        # Calculate distances from centroid to image center
        rel_y = cy - img_center_y
        rel_x = cx - img_center_x

        # Find extreme points in each direction using vectorized operations
        top_point = coords[np.argmin(coords[:, 0])]  # Minimum row (top)
        bottom_point = coords[np.argmax(coords[:, 0])]  # Maximum row (bottom)
        left_point = coords[np.argmin(coords[:, 1])]  # Minimum column (left)
        right_point = coords[np.argmax(coords[:, 1])]  # Maximum column (right)

        # Choose direction based on position relative to image center
        if abs(rel_y) > abs(rel_x):
            # Vertical direction dominates
            if rel_y < 0:
                # Object is above center - use top point
                label_y = top_point[0] - padding
                label_x = top_point[1]
                alignment = "center"
            else:
                # Object is below center - use bottom point
                label_y = bottom_point[0] + padding
                label_x = bottom_point[1]
                alignment = "center"
        # Horizontal direction dominates
        elif rel_x < 0:
            # Object is left of center - use left point
            label_x = left_point[1] - padding
            label_y = left_point[0]
            alignment = "right"
        else:
            # Object is right of center - use right point
            label_x = right_point[1] + padding
            label_y = right_point[0]
            alignment = "left"

        # Create label text
        label_text = f"{i + 1}"

        # Get text size
        text_size = cv2.getTextSize(label_text, font, font_scale, thickness)[0]

        # Adjust position based on alignment
        if alignment == "center":
            text_x = int(label_x - text_size[0] // 2)
            text_y = int(label_y)
        elif alignment == "right":
            text_x = int(label_x - text_size[0])
            text_y = int(label_y + text_size[1] // 2)  # Vertical centering
        else:  # 'left'
            text_x = int(label_x)
            text_y = int(label_y + text_size[1] // 2)  # Vertical centering

        # Ensure coordinates are within image bounds
        text_x = max(5, min(img_w - text_size[0] - 5, text_x))
        text_y = max(text_size[1] + 5, min(img_h - 5, text_y))

        # Add text to image
        cv2.putText(result, label_text, (text_x, text_y), font, font_scale, text_color, thickness)

    return result


def add_center_grid(image, grid_size=25, color=(0, 255, 0), thickness=1):
    # Create a copy of the image to avoid modifying the original
    result = image.copy()

    # Get image dimensions
    height, width = image.shape[:2]

    # Find the center of the image
    center_x, center_y = width // 2, height // 2

    # Calculate grid boundaries (ensure we have an odd number of grid lines)
    grid_width = (width // grid_size) * grid_size
    grid_height = (height // grid_size) * grid_size

    start_x = center_x - (grid_width // 2)
    start_y = center_y - (grid_height // 2)
    end_x = center_x + (grid_width // 2)
    end_y = center_y + (grid_height // 2)

    # Draw vertical lines
    for x in range(start_x, end_x + 1, grid_size):
        cv2.line(result, (x, start_y), (x, end_y), color, thickness)

    # Draw horizontal lines
    for y in range(start_y, end_y + 1, grid_size):
        cv2.line(result, (start_x, y), (end_x, y), color, thickness)

    # Draw center crosshair with a different color
    cv2.line(result, (center_x - 10, center_y), (center_x + 10, center_y), (0, 0, 255), 2)
    cv2.line(result, (center_x, center_y - 10), (center_x, center_y + 10), (0, 0, 255), 2)

    return result


def plot_label(image, region) -> None:
    # Detect LR wire
    orientation_degrees = (region.orientation * 180 / np.pi) % 15 * 15
    is_lr_wire = region.eccentricity > 0.95 and (60 <= orientation_degrees <= 120)

    if is_lr_wire:
        # Draw a line on the image
        cv2.putText(
            image,
            f"{region.label + 1}",
            (region.centroid[1], region.centroid[0]),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )


image_path = Path("storage/som_dataset")

modules = [
    None,
    KtaneComponent.big_button,
    KtaneComponent.morse_code,
    KtaneComponent.memory,
    None,
    KtaneComponent.password,
    KtaneComponent.venn,
    KtaneComponent.maze,
    KtaneComponent.wire_sequence,
    KtaneComponent.simon,
    KtaneComponent.wires,
    KtaneComponent.keypad,
    KtaneComponent.whos_on_first,
]
image_pairs = zip(
    modules,
    sorted(image_path.glob("screenshot*.png")),
    sorted(image_path.glob("segmentation*.png")),
    strict=True,
)

_module_writer = [None, *list(KtaneComponent)]
_has_writer = [mod in COMPONENT_WRITE_LABEL_MAPPER for mod in _module_writer]

label_writer = pl.from_dict(
    {"module": [str(mod) for mod in _module_writer], "has_writer": _has_writer}
)
st.write(label_writer)

for module, screenshot, segmentation in image_pairs:
    _ = st.header(module)
    col1, col2 = st.columns(2)
    with col1:
        _ = st.image(screenshot, caption="Screenshot", use_container_width=True)
    with col2:
        _ = st.image(segmentation, caption="Segmentation", use_container_width=True)

    segm_image = np.asarray(load_observation_from_bytes(segmentation.read_bytes()))
    labeled_segm = convert_colorful_segm_to_labeled(segm_image)
    regions = get_region_properties(labeled_segm)

    _ = regionprops_to_streamlit_table(regions)

    # Load the screenshot image
    image = np.asarray(load_observation_from_bytes(screenshot.read_bytes()))
    image = image.copy()

    # Load the segmentation image
    segm_image = np.asarray(load_observation_from_bytes(segmentation.read_bytes()))
    segm_image = segm_image.copy()

    som = SetOfMarksHandler()

    # Get a unique color for each region, these are equidistance hue values
    display_image = som.draw_region_outlines(image, segm_image, module)

    display_image = som.draw_labels(display_image, segm_image, module)

    # _ = plot_label(image, region)
    # image = add_center_grid(image)
    _ = st.image(display_image, use_container_width=True)

    _ = st.divider()
