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
        "hallucination_type": instance["hallucination"],
        "categories": instance["categories"],
        "index": instance["index"],
    }


@weave.op
def preprocess_defuser_vqa_open_ended_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """Convert the instance to rename the fields to match the model (defuser VQA open-ended)."""
    input_images = instance["input_images"]
    if isinstance(input_images[0], str):
        input_images = [Image.open(image_path).copy() for image_path in input_images]
    elif isinstance(input_images[0], dict) and "bytes" in input_images[0]:
        input_images = [Image.open(io.BytesIO(image["bytes"])).copy() for image in input_images]
    return {
        "model_input": instance["model_input"],
        "ground_truth": instance["ground_truth"],
        "input_type": instance["input_type"],
        "input_images": input_images,
        "hallucination_type": instance["hallucination"],
        "categories": instance["categories"],
        "index": instance["index"],
    }


@weave.op
def preprocess_defuser_vqa_mcq_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """Convert the instance to rename the fields to match the model (defuser VQA MCQ)."""
    # Format as A, B, C, ... and find ground truth letter
    letter = "A"
    formatted_lines = []
    ground_truth_letter = None

    for index, option in enumerate(instance["options"]):
        letter = chr(ord("A") + index)  # Convert index to letter (A, B, C, ...)
        formatted_lines.append(f"{letter}. {option}")
        if option == instance["ground_truth"]:
            ground_truth_letter = letter

    if ground_truth_letter is None:
        logger.error(
            "Ground truth not found in options",
            ground_truth=instance["ground_truth"],
            options=instance["options"],
        )
    formatted_options = "\n".join(formatted_lines)

    model_input = f"{instance['model_input']}\n\n{formatted_options}"
    input_images = instance["input_images"]
    if isinstance(input_images[0], str):
        input_images = [Image.open(image_path).copy() for image_path in input_images]
    elif isinstance(input_images[0], dict) and "bytes" in input_images[0]:
        input_images = [Image.open(io.BytesIO(image["bytes"])).copy() for image in input_images]
    return {
        "model_input": model_input,
        "ground_truth": ground_truth_letter,
        "input_type": instance["input_type"],
        "input_images": input_images,
        "hallucination_type": instance["hallucination"],
        "options": instance["options"],
        "ground_truth_str": instance["ground_truth"],
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
