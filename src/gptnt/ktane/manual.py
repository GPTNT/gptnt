from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, HttpUrl, validate_call
from pydantic_settings import BaseSettings, SettingsConfigDict
from structlog import get_logger

from gptnt.common.paths import Paths
from gptnt.common.prompt_cache import PromptCache

logger = get_logger()


MANUAL_NUM_PAGES = 23
"""Number of pages in the KTANE manual."""

NEEDY_MODULE_PAGE_NUMS = tuple(range(17, 21))
"""Page numbers for needy modules in the KTANE manual.

Index start at 1.
"""

APPENDIX_PAGES = (21, 22, 23)
"""Page numbers for appendix pages in the KTANE manual.

Index start at 1.
"""

EXPLAINER_PAGES_TO_REMOVE = (1, 2, 4)
"""Page numbers for explainer pages to remove from the KTANE manual.

Index start at 1.
"""

MANUAL_PAGE_IDENTIFIER_STRING = "8/28/2020 KeepTalkingandNobodyExplodes-BombDefusalManual-en-v1"
"""A string that helps identify a manual page the KTANE manual in the text.

There are probably better ways to do this, but for now, this is a good enough heuristic.
"""


type PageNumType = Annotated[int, Field(gt=0, le=MANUAL_NUM_PAGES, description="Page number")]


class KtaneManualPaths(BaseSettings):
    """Paths for the KTANE manual.

    All of these can be set from environment variables by prefixing the name with "MANUAL_". For
    example, to set the local path, use "MANUAL_LOCAL=/path/to/manual.pdf".

    The environment variable will be used if it is set, otherwise the default value will be used.
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="_", env_nested_max_split=1, env_prefix="MANUAL_"
    )

    remote: HttpUrl = HttpUrl(
        "https://www.bombmanual.com/print/KeepTalkingAndNobodyExplodes-BombDefusalManual-v1.pdf"
    )

    root: Path = Paths().storage.joinpath("manual")

    local: Path = root.joinpath("ktane-manual.pdf")

    images_orig_dir: Path = root.joinpath("images/raw")
    images_small_dir: Path = root.joinpath("images/640_h")
    text_dir: Path = root.joinpath("text")

    @validate_call
    def load_text(self, page_num: PageNumType) -> str:
        """Load the text for a given page number."""
        text_path = self.text_dir.joinpath(f"page_{page_num}.txt")

        if not text_path.exists():
            raise FileNotFoundError("Text file does not exist, and it should?")
        try:
            return PromptCache.get_text(text_path)
        except KeyError:
            logger.warning("PromptCache not initialised, loading text directly from disk")
            return text_path.read_text()

    @validate_call
    def load_image(
        self, page_num: PageNumType, *, kind: Literal["orig", "small"] = "small"
    ) -> bytes:
        """Load the image for a given page number, as bytes.

        We can load two kinds of images: the original and the small version. Default to small.
        """
        kind_switcher = {"orig": self.images_orig_dir, "small": self.images_small_dir}
        image_path = kind_switcher[kind].joinpath(f"page_{page_num}.png")

        if not image_path.exists():
            raise FileNotFoundError("Image file does not exist, and it should?")

        try:
            return PromptCache.get_bytes(image_path)
        except KeyError:
            logger.warning("PromptCache not initialized, loading image directly from disk")
            return image_path.read_bytes()
