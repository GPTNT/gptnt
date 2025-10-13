from functools import lru_cache

import structlog
from pydantic_ai import BinaryContent

from gptnt.ktane.manual import (
    APPENDIX_PAGES,
    EXPLAINER_PAGES_TO_REMOVE,
    MANUAL_NUM_PAGES,
    NEEDY_MODULE_PAGE_NUMS,
    KtaneManualPaths,
)

logger = structlog.get_logger()


@lru_cache(maxsize=1)
def load_manual_as_prompt(
    *,
    num_pages: int = MANUAL_NUM_PAGES,
    skip_needy_modules: bool = True,
    skip_explainer_pages: bool = True,
    skip_appendix_pages: bool = False,
) -> list[str | BinaryContent]:
    """Load the content for the manual."""
    logger.debug(f"Loading {num_pages} pages of the manual")
    manual_paths = KtaneManualPaths()

    pages_to_skip: list[int] = [
        *(NEEDY_MODULE_PAGE_NUMS if skip_needy_modules else []),
        *(EXPLAINER_PAGES_TO_REMOVE if skip_explainer_pages else []),
        *(APPENDIX_PAGES if skip_appendix_pages else []),
    ]

    manual = []
    for page_num in range(1, num_pages + 1):
        if page_num in pages_to_skip:
            logger.debug(f"Skipping page {page_num} of the manual")
            continue

        # Load the text for the page first
        text = manual_paths.load_text(page_num)
        manual.append(text)

        # Load the image for the page afterward
        image = manual_paths.load_image(page_num, kind="small")
        image = BinaryContent(image, media_type="image/png")
        manual.append(image)

    return manual
