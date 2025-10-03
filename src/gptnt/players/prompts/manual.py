from functools import lru_cache

import structlog
from pydantic_ai import BinaryContent

from gptnt.ktane.manual import MANUAL_NUM_PAGES, NEEDY_MODULE_PAGE_NUMS, KtaneManualPaths

logger = structlog.get_logger()


@lru_cache(maxsize=1)
def load_manual_as_prompt(
    *, num_pages: int = MANUAL_NUM_PAGES, skip_needy_modules: bool = True
) -> list[str | BinaryContent]:
    """Load the content for the manual."""
    logger.debug(f"Loading {num_pages} pages of the manual")
    manual_paths = KtaneManualPaths()

    manual = []
    for page_num in range(1, num_pages + 1):
        if skip_needy_modules and page_num in NEEDY_MODULE_PAGE_NUMS:
            # Skip the needy module pages
            continue

        # Load the text for the page first
        text = manual_paths.load_text(page_num)
        manual.append(text)

        # Load the image for the page afterward
        image = manual_paths.load_image(page_num, kind="512")
        image = BinaryContent(image, media_type="image/png")
        manual.append(image)

    return manual
