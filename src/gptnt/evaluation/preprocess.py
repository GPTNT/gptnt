import io
from typing import Any

import structlog
import weave
from PIL import Image

from gptnt.ktane.manual import KtaneManualPaths

logger = structlog.get_logger()

ktane_manual_paths = KtaneManualPaths()


@weave.op
def preprocess_grounding_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """Convert the instance to rename the fields to match the model."""
    som_image = instance["som_image"]

    # if a image path is passed instead of an image, load the image
    if isinstance(som_image, str):
        som_image = Image.open(som_image).copy()

    if isinstance(som_image, dict) and "bytes" in som_image:
        som_image = Image.open(io.BytesIO(som_image["bytes"])).copy()

    return {
        "model_input": instance["model_input"],
        "ground_truth": instance["ground_truth"],
        "input_type": instance["input_type"],
        "som_image": som_image,
        "categories": instance["categories"],
        "index": instance["index"],
    }


@weave.op
def preprocess_expert_vqa_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """Convert the instance to rename the fields to match the model (expert VQA)."""
    page_numbers = instance["page_number"]
    manual_content: list[str | Image.Image] = []

    for page_number in page_numbers:
        manual_page_text = ktane_manual_paths.load_text(page_number)
        manual_page_image_bytes: bytes = ktane_manual_paths.load_image(page_number)
        manual_page_image = Image.open(io.BytesIO(manual_page_image_bytes))

        manual_content.append(manual_page_text)
        manual_content.append(manual_page_image)

    return {
        "categories": instance["categories"],
        "model_input": instance["model_input"],
        "manual": manual_content,
        "ground_truth": instance["ground_truth"],
        "input_type": "expert_vqa",
        "index": instance["index"],
        **instance["metadata"],  # noqa: WPS110
    }
