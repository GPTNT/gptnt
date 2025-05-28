import itertools
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import structlog

from gptnt.common.paths import Paths

paths = Paths()

logger = structlog.get_logger()


@dataclass(kw_only=True)
class PromptCache:
    """Singleton cache for all prompt files."""

    cache: ClassVar[dict[Path, str | bytes]] = {}

    text_extensions: ClassVar[set[str]] = {".md", ".txt"}
    binary_extensions: ClassVar[set[str]] = {".png"}

    @classmethod
    def initialise(cls, *directory_paths: Path) -> None:
        """Initialize the cache by loading all files from a directory."""
        logger.info("Caching all prompt files...")
        cls.cache = {}
        text_files = itertools.chain.from_iterable(
            [
                directory_path.rglob(f"*{ext}")
                for ext in cls.text_extensions
                for directory_path in directory_paths
            ]
        )
        binary_files = itertools.chain.from_iterable(
            [
                directory_path.rglob(f"*{ext}")
                for ext in cls.binary_extensions
                for directory_path in directory_paths
            ]
        )

        for file_path in text_files:
            cls.cache[file_path] = file_path.read_text()
        for file_path in binary_files:
            cls.cache[file_path] = file_path.read_bytes()

        logger.info(f"Cached {len(cls.cache)} files")

    @classmethod
    def get_text(cls, path: Path) -> str:
        """Get cached file content by filename."""
        try:
            text_content = cls.cache[path]
        except KeyError:
            logger.warning(
                "Prompt file not found in cache", path=path, available_files=list(cls.cache.keys())
            )
            raise

        if not isinstance(text_content, str):
            logger.error(
                "Cached content is not a string", path=path, content_type=type(text_content)
            )
            raise TypeError(f"Cached content for {path} is not a string")
        return text_content

    @classmethod
    def get_bytes(cls, path: Path) -> bytes:
        """Get cached file content by filename."""
        try:
            binary_content = cls.cache[path]
        except KeyError:
            logger.warning(
                "Prompt file not found in cache", path=path, available_files=list(cls.cache.keys())
            )
            raise

        if not isinstance(binary_content, bytes):
            logger.error(
                "Cached content is not bytes", path=path, content_type=type(binary_content)
            )
            raise TypeError(f"Cached content for {path} is not bytes")
        return binary_content
