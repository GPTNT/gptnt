import types
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, HttpUrl, validate_call
from pydantic_settings import BaseSettings, SettingsConfigDict

from gptnt.common.paths import Paths

MANUAL_NUM_PAGES = 23
"""Number of pages in the legacy English KTANE manual."""

NEEDY_MODULE_PAGE_NUMS = tuple(range(17, 21))
"""One-based page numbers for needy modules in the legacy manual."""

APPENDIX_PAGES = (21, 22, 23)
"""One-based appendix page numbers in the legacy manual."""

EXPLAINER_PAGES_TO_REMOVE = (1, 2, 4)
"""One-based explainer page numbers omitted from the legacy prompt."""

MANUAL_PAGE_IDENTIFIER_STRING = "8/28/2020 KeepTalkingandNobodyExplodes-BombDefusalManual-en-v1"
"""Text used to identify pages from the legacy manual."""

MODULE_TO_PAGE_NUM_MAP = types.MappingProxyType(
    {
        "Wires": (5,),
        "BigButton": (6,),
        "Keypad": (7,),
        "Simon": (8,),
        "WhosOnFirst": (9, 10),
        "Memory": (11,),
        "Morse": (12,),
        "Venn": (13,),
        "WireSequence": (14,),
        "Maze": (15,),
        "Password": (16,),
    }
)

type PageNumType = Annotated[int, Field(gt=0, le=MANUAL_NUM_PAGES, description="Page number")]
type ImageSizeKind = Literal["orig", "small"]


class KtaneManualPaths(BaseSettings):
    """Filesystem paths for the tracked legacy manual assets."""

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
    def get_text_path(self, page_num: PageNumType) -> Path:
        """Get the text path for a page."""
        return self.text_dir.joinpath(f"page_{page_num}.txt")

    @validate_call
    def get_image_path(self, page_num: PageNumType, *, kind: ImageSizeKind = "small") -> Path:
        """Get one of the stored image representations for a page."""
        kind_switcher = {"orig": self.images_orig_dir, "small": self.images_small_dir}
        return kind_switcher[kind].joinpath(f"page_{page_num}.png")
