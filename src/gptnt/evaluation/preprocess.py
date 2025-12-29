import io
import json
from collections.abc import Callable
from typing import Any

import structlog
import weave
from PIL import Image

from gptnt.prompts.manual import KtaneManualLoader

logger = structlog.get_logger()

ktane_manual_paths = KtaneManualLoader()

type PostprocessInputsFunc = Callable[[dict[str, Any]], dict[str, Any]]


def load_image(image: str | dict[str, Any] | None) -> Image.Image | None:
    """Load an image from a path or bytes dict."""
    if isinstance(image, str):
        return Image.open(image).copy()
    if isinstance(image, dict) and "bytes" in image:
        return Image.open(io.BytesIO(image["bytes"])).copy()
    if image is None:
        return None
    raise ValueError("Invalid image format")


@weave.op
def preprocess_grounding_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """Convert the instance to rename the fields to match the model."""
    som_image = load_image(instance["som_image"])
    return {
        **instance,
        "model_input": [som_image, instance["model_input"]],
        "question": instance["model_input"],
        "som_image": som_image,
        "segmentation_mask": load_image(instance["segmentation_mask"]),
        "frames": [load_image(image) for image in instance["frames"]],
    }


@weave.op
def preprocess_defuser_vqa_open_ended_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """Convert the instance to rename the fields to match the model (defuser VQA open-ended)."""
    input_images = [load_image(image) for image in instance["input_images"]]

    return {
        **instance,
        "model_input": [*input_images, instance["model_input"]],
        "question": instance["model_input"],
        "input_images": [load_image(image) for image in instance["input_images"]],
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
        raise ValueError("Ground truth answer not found in options.")

    formatted_options = "\n".join(formatted_lines)

    model_input = f"{instance['model_input']}\n\n{formatted_options}"
    input_images = [load_image(image) for image in instance["input_images"]]

    return {
        **instance,
        "model_input": [*input_images, model_input],
        "ground_truth": ground_truth_letter,
        "ground_truth_str": instance["ground_truth"],
        "question": instance["model_input"],
        "input_images": input_images,
    }


@weave.op
def preprocess_expert_ocr_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """Convert the instance to rename the fields to match the model (manual OCR)."""
    manual_image = load_image(instance["image"])

    return {**instance, "model_input": [manual_image, instance["question"]]}


@weave.op
def preprocess_expert_grounding_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """Convert the instance to rename the fields to match the model."""
    image = load_image(instance["image"])

    return {**instance, "model_input": [image, instance["question"]], "image": image}


@weave.op
def preprocess_expert_vqa_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """Convert the instance to rename the fields to match the model (expert VQA)."""
    manual_content: list[str | Image.Image] = []

    # Extract the pieces, and sort them by page number
    manual_content_iterator = sorted(
        zip(instance["page_number"], instance["images"], instance["manual_texts"], strict=True),
        key=lambda group: group[0],
    )

    for _, image, text in manual_content_iterator:
        loaded_image = load_image(image)
        assert loaded_image is not None

        manual_content.append(text)
        manual_content.append(loaded_image)

    return {
        **instance,
        "model_input": [*manual_content, instance["model_input"]],
        "input_type": "expert_vqa",
        "metadata": json.loads(instance["metadata"])
        if isinstance(instance["metadata"], str)
        else instance["metadata"],
        "images": [load_image(img) for img in instance["images"]],
    }
