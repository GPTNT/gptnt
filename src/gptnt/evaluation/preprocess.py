import io
import json
from collections.abc import Callable
from typing import Any

import numpy as np
import structlog
import weave
from numpy.typing import NDArray
from PIL import Image

from gptnt.ktane.manual import MODULE_TO_PAGE_NUM_MAP
from gptnt.ktane.state.modules import KtaneComponent
from gptnt.prompts.manual import KtaneManualLoader

logger = structlog.get_logger()

ktane_manual_paths = KtaneManualLoader()

type PostprocessInputsFunc = Callable[[dict[str, Any]], dict[str, Any]]


def load_image(image: str | dict[str, Any] | Any) -> Image.Image:
    """Load an image from a path or bytes dict."""
    if isinstance(image, Image.Image):
        return image.copy()
    if isinstance(image, str):
        return Image.open(image).copy()
    if isinstance(image, dict) and "bytes" in image:
        return Image.open(io.BytesIO(image["bytes"])).copy()

    raise ValueError("Invalid image format")


def convert_ground_truth_to_binary_mask(instance: dict[str, Any]) -> NDArray[np.uint8]:
    """Convert ground truth to binary mask image."""
    segmentation_mask = load_image(instance["segmentation_mask"])
    width, height = segmentation_mask.size
    binary_mask_numpy = np.array(list(instance["ground_truth"]), dtype=np.uint8)
    return binary_mask_numpy.reshape(height, width)


def preprocess_grounding_user_text(object_description: str) -> str:
    """Preprocess the object description for grounding tasks."""
    return f"Click on the {object_description}."


def preprocess_grounding_coordinates_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """Convert the instance to rename the fields to match the model."""
    input_image = load_image(instance["frames"][-1])

    # If it's a hallucination instance, the ground truth is a string and not an image.
    if instance["hallucination"] is not None and instance["hallucination"] != "None":
        ground_truth = instance["ground_truth"]
        binary_mask = None
    else:
        ground_truth = convert_ground_truth_to_binary_mask(instance)
        binary_mask = Image.fromarray(ground_truth * 255)

    input_text = preprocess_grounding_user_text(instance["model_input"])
    return {
        **instance,
        "model_input": [input_image, input_text],  # noqa: WPS226
        "question": input_text,
        "som_image": load_image(instance["som_image"]),
        "segmentation_mask": load_image(instance["segmentation_mask"]),
        "frames": [load_image(image) for image in instance["frames"]],
        "ground_truth": ground_truth,
        "binary_mask": binary_mask,
    }


def preprocess_grounding_set_of_marks_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """Convert the instance to rename the fields to match the model."""
    som_image = load_image(instance["som_image"])
    input_text = preprocess_grounding_user_text(instance["model_input"])
    return {
        **instance,
        "model_input": [som_image, input_text],
        "question": input_text,
        "som_image": som_image,
        "segmentation_mask": load_image(instance["segmentation_mask"]),
        "frames": [load_image(image) for image in instance["frames"]],
    }


def preprocess_defuser_vqa_open_ended_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """Convert the instance to rename the fields to match the model (defuser VQA open-ended)."""
    input_images = [load_image(image) for image in instance["input_images"]]

    return {
        **instance,
        "model_input": [*input_images, instance["model_input"]],
        "question": instance["model_input"],
        "input_images": input_images,
        "preview": input_images[-1],
    }


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
        "preview": input_images[-1],
    }


def preprocess_expert_ocr_instance(
    instance: dict[str, Any], *, include_manual_text: bool = False
) -> dict[str, Any]:
    """Convert the instance to rename the fields to match the model (manual OCR)."""
    manual_content: list[str | Image.Image] = []
    if include_manual_text:
        module = KtaneComponent(instance["module"])
        pages = MODULE_TO_PAGE_NUM_MAP[module]
        manual_content.extend(ktane_manual_paths.load_text(page_num) for page_num in pages)

    manual_image = manual_content.append(load_image(instance["image"]))

    return {
        **instance,
        "model_input": [*manual_content, instance["question"]],
        "image": manual_image,
    }


@weave.op
def preprocess_expert_grounding_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """Convert the instance to rename the fields to match the model."""
    image = load_image(instance["image"])

    return {**instance, "model_input": [image, instance["question"]], "image": image}


def preprocess_expert_vqa_instance(
    instance: dict[str, Any], *, include_manual: bool = True
) -> dict[str, Any]:
    """Convert the instance to rename the fields to match the model (expert VQA)."""
    manual_content: list[str | Image.Image] = []

    # Extract the pieces, and sort them by page number
    manual_content_iterator = sorted(
        zip(instance["page_number"], instance["images"], instance["manual_texts"], strict=True),
        key=lambda group: group[0],
    )
    if include_manual:
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
        "preview": load_image(instance["images"][-1]),
    }
