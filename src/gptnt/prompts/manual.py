import io

import structlog
from pydantic_ai import BinaryContent

from gptnt.common.image_ops import ImageDimensions, load_observation_from_bytes
from gptnt.ktane.manuals.artifacts import ManualArtifact
from gptnt.processors.image_resizer import ImageResizer

logger = structlog.get_logger()


def _resize_manual_image(image: bytes, *, page_number: int, resizer: ImageResizer) -> bytes:
    """Resize one manual PNG in memory while preserving its aspect ratio."""
    logger.info(
        f"Resizing manual page {page_number} to fit target "
        f"({resizer.target_width}x{resizer.target_height})"
    )
    pil_image = load_observation_from_bytes(image)
    resized_image = resizer.resize_image(pil_image)
    with io.BytesIO() as output_bytes:
        resized_image.save(output_bytes, format="PNG")
        return output_bytes.getvalue()


def load_prepared_manual_as_prompt(
    artifact: ManualArtifact, *, image_dimensions: ImageDimensions | None = None
) -> list[str | BinaryContent]:
    """Build a prompt from one loaded manual artifact."""
    resizer = (
        ImageResizer(
            target_width=image_dimensions.short_side, target_height=image_dimensions.long_side
        )
        if image_dimensions
        else None
    )
    prompt: list[str | BinaryContent] = []
    for page_number, (text, image) in enumerate(artifact.pages, start=1):
        prompt.append(text)
        resized = (
            _resize_manual_image(image, page_number=page_number, resizer=resizer)
            if resizer
            else image
        )
        prompt.append(BinaryContent(resized, media_type="image/png"))
    return prompt
