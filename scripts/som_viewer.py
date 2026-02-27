from pathlib import Path

import numpy as np
import polars as pl
import streamlit as st
from PIL import Image, ImageDraw

from gptnt.common.image_ops import load_observation_from_bytes
from gptnt.ktane.state.modules import KtaneComponent
from gptnt.processors.set_of_marks import (
    COMPONENT_WRITE_LABEL_MAPPER,
    AnnotationBackgroundParams,
    AnnotationTextParams,
    MaskDrawingParams,
    SetOfMarksHandler,
    convert_colorful_segm_to_labeled,
    get_centered_stepped_coordinate,
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


image_path = Path("storage/fixtures/som_dataset")

NAME_TO_MODULE: dict[str, KtaneComponent | None] = {
    "bomb": None,
    "button": KtaneComponent.big_button,
    "keypad": KtaneComponent.keypad,
    "maze": KtaneComponent.maze,
    "memory": KtaneComponent.memory,
    "morse": KtaneComponent.morse_code,
    "password": KtaneComponent.password,
    "simon": KtaneComponent.simon,
    "venn": KtaneComponent.venn,
    "whoseonfirst": KtaneComponent.whos_on_first,
    "wires": KtaneComponent.wires,
    "wireseq": KtaneComponent.wire_sequence,
}


def stem_to_module(stem: str) -> KtaneComponent | None:
    base = stem.removesuffix("-screen").split("-")[0]
    return NAME_TO_MODULE.get(base)


screen_files = sorted(image_path.glob("*-screen.png"))
image_pairs = []
for screen in screen_files:
    segm = screen.with_name(screen.name.replace("-screen.png", "-segm.png"))
    if segm.exists():
        image_pairs.append((stem_to_module(screen.stem), screen, segm))


_module_writer = [None, *list(KtaneComponent)]
_has_writer = [mod in COMPONENT_WRITE_LABEL_MAPPER for mod in _module_writer]

label_writer = pl.from_dict(
    {"module": [str(mod) for mod in _module_writer], "has_writer": _has_writer}
)
st.write(label_writer)
with st.sidebar:
    add_labels = st.toggle("Add labels", value=True)
    add_mask_outline = st.toggle("Add mask outline", value=True)
    bw_outside_mask = st.toggle("Black and white outside mask", value=False)
    _ = st.header("Annotation Background")
    annotation_bg_padding = st.number_input(
        "Annotation background padding", min_value=0, max_value=100, value=3, step=1
    )
    annotation_bg_alpha = st.number_input(
        "Annotation background alpha", min_value=0.0, max_value=1.0, value=0.75, step=0.01
    )
    _ = st.header("Annotation Text")
    annotation_text_font = st.number_input(
        "Annotation text font", min_value=0, max_value=10, value=2, step=1
    )
    annotation_text_scale = st.number_input(
        "Annotation text scale", min_value=0.0, max_value=10.0, value=0.7, step=0.01
    )
    annotation_text_thickness = st.number_input(
        "Annotation text thickness", min_value=0, max_value=10, value=1, step=1
    )
    annotation_text_space_between = st.number_input(
        "Space between annotation text", min_value=0, max_value=10, value=2, step=1
    )
    _ = st.header("Mask")
    mask_thickness = st.number_input("Mask thickness", min_value=0, max_value=10, value=1, step=1)
    mask_alpha = st.number_input("Mask alpha", min_value=0.0, max_value=1.0, value=0.10, step=0.01)
    square_size = None  # st.number_input("Minimum square size", min_value=0, step=1)

som = SetOfMarksHandler(
    annotation_background_params=AnnotationBackgroundParams(
        padding=annotation_bg_padding, alpha=annotation_bg_alpha
    ),
    annotation_text_params=AnnotationTextParams(
        font=annotation_text_font,
        font_scale=annotation_text_scale,
        thickness=annotation_text_thickness,
        space_between_boxes=annotation_text_space_between,
    ),
    mask_drawing_params=MaskDrawingParams(
        mask_thickness=mask_thickness,
        soft_mask_alpha=mask_alpha,
        bw_outside_mask=bw_outside_mask,
        mask_highlight_size=square_size,
    ),
    add_labels=add_labels,
    add_mask_outline=add_mask_outline,
)


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

    display_image = som.run(
        observation=image, colorful_image=segm_image, zoomed_in_component=module
    )

    pil_img = Image.fromarray(display_image)
    draw = ImageDraw.Draw(pil_img)
    for region in regions:
        if module == KtaneComponent.wire_sequence:
            flipped_coords = get_centered_stepped_coordinate(region)
        else:
            flipped_coords = region.centroid
        coords = (flipped_coords[1], flipped_coords[0])

        size = 5
        draw.line(
            (coords[0] - size, coords[1] - size, coords[0] + size, coords[1] + size),
            fill="red",
            width=2,
        )
        draw.line(
            (coords[0] - size, coords[1] + size, coords[0] + size, coords[1] - size),
            fill="red",
            width=2,
        )

    # _ = plot_label(image, region)
    # image = add_center_grid(image)
    _ = st.image(pil_img, use_container_width=True)

    # # region colors
    # for region in regions:
    #     color = get_region_color(image, segm_image, region, module, 0, 0)
    #     hsv_color = colorsys.rgb_to_hsv(*color)
    #     st.write(f"Region {region.label} color: {color}, HSV: {hsv_color}")

    _ = st.divider()
