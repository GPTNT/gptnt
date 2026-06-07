from pathlib import Path

import logfire
import numpy as np
from PIL import Image, ImageDraw

from gptnt.core.common.image_ops import load_observation_from_bytes
from gptnt.core.ktane.state.modules import KtaneComponent
from gptnt.core.processors.set_of_marks import (
    AnnotationBackgroundParams,
    AnnotationTextParams,
    MaskDrawingParams,
    SetOfMarksHandler,
    convert_colorful_segm_to_labeled,
    get_centered_stepped_coordinate,
    get_region_properties,
)

logfire.configure()

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


def profile_som_pipeline():
    image_path = Path("storage/fixtures/som_dataset")

    screen_files = sorted(image_path.glob("*-screen.png"))
    image_pairs = []
    for screen in screen_files:
        segm = screen.with_name(screen.name.replace("-screen.png", "-segm.png"))
        if segm.exists():
            image_pairs.append((stem_to_module(screen.stem), screen, segm))

    som = SetOfMarksHandler(
        annotation_background_params=AnnotationBackgroundParams(padding=3, alpha=0.75),
        annotation_text_params=AnnotationTextParams(
            font=2, font_scale=0.7, thickness=1, space_between_boxes=2
        ),
        mask_drawing_params=MaskDrawingParams(
            mask_thickness=1, soft_mask_alpha=0.1, bw_outside_mask=False, mask_highlight_size=None
        ),
        add_labels=True,
        add_mask_outline=True,
        mark_type="alphabet",
    )

    with logfire.span("profile_som_pipeline"):
        for module, screenshot, segmentation in image_pairs:
            name = screenshot.stem.removesuffix("-screen")

            with logfire.span("{name}", name=name, module=str(module)):
                with logfire.span("read_bytes"):
                    screenshot_bytes = screenshot.read_bytes()
                    segmentation_bytes = segmentation.read_bytes()

                with logfire.span("load_images"):
                    image = np.asarray(load_observation_from_bytes(screenshot_bytes)).copy()
                    segm_image = np.asarray(load_observation_from_bytes(segmentation_bytes)).copy()

                with logfire.span("convert_to_labeled"):
                    labeled_segm = convert_colorful_segm_to_labeled(segm_image)

                with logfire.span("get_region_props"):
                    regions = get_region_properties(labeled_segm)

                with logfire.span("som_run"):
                    display_image = som.run(
                        observation=image, colorful_image=segm_image, zoomed_in_component=module
                    )

                with logfire.span("draw_crosshairs"):
                    pil_img = Image.fromarray(display_image)
                    draw = ImageDraw.Draw(pil_img)
                    for region in regions:
                        flipped_coords = (
                            get_centered_stepped_coordinate(region)
                            if module == KtaneComponent.wire_sequence
                            else region.centroid
                        )
                        coords = (flipped_coords[1], flipped_coords[0])
                        size = 5
                        draw.line(
                            (
                                coords[0] - size,
                                coords[1] - size,
                                coords[0] + size,
                                coords[1] + size,
                            ),
                            fill="red",
                            width=2,
                        )
                        draw.line(
                            (
                                coords[0] - size,
                                coords[1] + size,
                                coords[0] + size,
                                coords[1] - size,
                            ),
                            fill="red",
                            width=2,
                        )


if __name__ == "__main__":
    profile_som_pipeline()
