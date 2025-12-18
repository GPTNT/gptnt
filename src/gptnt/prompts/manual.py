import io
from dataclasses import dataclass, field
from functools import lru_cache

import structlog
from pydantic_ai import BinaryContent

from gptnt.common.image_ops import ImageDimensions, load_observation_from_bytes
from gptnt.ktane.manual import (
    APPENDIX_PAGES,
    EXPLAINER_PAGES_TO_REMOVE,
    MANUAL_NUM_PAGES,
    NEEDY_MODULE_PAGE_NUMS,
    ImageSizeKind,
    KtaneManualPaths,
    PageNumType,
)
from gptnt.processors.image_resizer import ImageResizer
from gptnt.prompts.prompt_cache import PromptCache

logger = structlog.get_logger()

manual_paths = KtaneManualPaths()


@lru_cache
def load_manual_text(page_num: PageNumType) -> str:
    """Load the text for a given page number."""
    text_path = manual_paths.get_text_path(page_num)
    return PromptCache.get_text(text_path)


@lru_cache
def load_manual_image(
    page_num: PageNumType,
    *,
    image_kind: ImageSizeKind = "small",
    image_resizer: ImageResizer | None = None,
) -> bytes:
    """Load the image for a given page number, as bytes.

    We can load two kinds of images: the original and the small version. Default to small.
    """
    image_path = manual_paths.get_image_path(page_num, kind=image_kind)
    image_as_bytes = PromptCache.get_bytes(image_path)
    # Do image resizing if needed on top of that
    if image_resizer is not None:
        logger.info(
            f"Resizing manual page {page_num} to fit target ({image_resizer.target_width}x{image_resizer.target_height})"
        )
        pil_image = load_observation_from_bytes(image_as_bytes)
        resized_image = image_resizer.resize_image(pil_image)
        with io.BytesIO() as output_bytes:
            resized_image.save(output_bytes, format="PNG")
            image_as_bytes = output_bytes.getvalue()

    return image_as_bytes


@dataclass(kw_only=True)
class KtaneManualLoader:
    """Class to load the manual pages as needed.

    This also does not complain if the PromptCache is not initialised, and will load directly from
    disk, which is a useful utility that is used EVERYWHERE.
    """

    manual_paths: KtaneManualPaths = field(default_factory=KtaneManualPaths)
    image_resizer: ImageResizer | None = None

    def load_image(self, page_num: PageNumType, *, kind: ImageSizeKind = "small") -> bytes:
        """Load the image for a given page number."""
        return load_manual_image(page_num, image_kind=kind, image_resizer=self.image_resizer)

    def load_text(self, page_num: PageNumType) -> str:
        """Load the text for a given page number."""
        return load_manual_text(page_num)


@lru_cache
def load_manual_as_prompt(
    *,
    num_pages: int = MANUAL_NUM_PAGES,
    skip_needy_modules: bool = True,
    skip_explainer_pages: bool = True,
    skip_appendix_pages: bool = False,
    image_dimensions: ImageDimensions | None = None,
) -> list[str | BinaryContent]:
    """Load the content for the manual.

    Because certain models also need resized images, we also do that here and cache them in the
    memory for nice and quick access. When using `image_dimensions`, we resize images using the
    long and short sides to preserve aspect ratio.
    """
    logger.debug(f"Loading {num_pages} pages of the manual")

    pages_to_skip: list[int] = [
        *(NEEDY_MODULE_PAGE_NUMS if skip_needy_modules else []),
        *(EXPLAINER_PAGES_TO_REMOVE if skip_explainer_pages else []),
        *(APPENDIX_PAGES if skip_appendix_pages else []),
    ]

    manual_loader = KtaneManualLoader(
        image_resizer=ImageResizer(
            target_width=image_dimensions.short_side, target_height=image_dimensions.long_side
        )
        if image_dimensions
        else None
    )

    manual = []
    for page_num in range(1, num_pages + 1):
        if page_num in pages_to_skip:
            logger.debug(f"Skipping page {page_num} of the manual")
            continue

        # Load the text for the page first
        text = manual_loader.load_text(page_num)
        manual.append(text)

        # Load the image for the page afterward
        image = manual_loader.load_image(page_num, kind="small")
        image = BinaryContent(image, media_type="image/png")
        manual.append(image)

    return manual
