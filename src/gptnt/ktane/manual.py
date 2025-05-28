from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, HttpUrl, validate_call
from pydantic_settings import BaseSettings, SettingsConfigDict
from structlog import get_logger

from gptnt.common.paths import Paths

logger = get_logger()


MANUAL_NUM_PAGES = 23
"""Number of pages in the KTANE manual."""

NEEDY_MODULE_PAGE_NUMS = tuple(range(17, 21))
"""Page numbers for needy modules in the KTANE manual."""

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
    images_512_dir: Path = root.joinpath("images/512_512")
    text_dir: Path = root.joinpath("text")

    @validate_call
    def load_text(self, page_num: PageNumType) -> str:
        """Load the text for a given page number."""
        text_path = self.text_dir.joinpath(f"page_{page_num}.txt")

        if not text_path.exists():
            raise FileNotFoundError("Text file does not exist, and it should?")

        return text_path.read_text()

    @validate_call
    def load_image(self, page_num: PageNumType, *, kind: Literal["orig", "512"] = "512") -> bytes:
        """Load the image for a given page number, as bytes.

        We can load two kinds of images: the original and the 512x512 version. Default to 512x512.
        """
        kind_switcher = {"orig": self.images_orig_dir, "512": self.images_512_dir}
        image_path = kind_switcher[kind].joinpath(f"page_{page_num}.png")

        if not image_path.exists():
            raise FileNotFoundError("Image file does not exist, and it should?")

        return image_path.read_bytes()
