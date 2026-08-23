import itertools
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import structlog

logger = structlog.get_logger()


@dataclass(kw_only=True)
class PromptCache:
    """Singleton cache for all prompt files."""

    cache: ClassVar[dict[Path, str]] = {}

    text_extensions: ClassVar[set[str]] = {".md", ".txt"}

    @classmethod
    def initialise(cls, *directory_paths: Path) -> None:
        """Initialize the cache by loading all files from a directory."""
        logger.debug("Caching all prompt files...")
        cls.cache = {}
        text_files = itertools.chain.from_iterable(
            [
                directory_path.rglob(f"*{ext}")
                for ext in cls.text_extensions
                for directory_path in directory_paths
            ]
        )
        for file_path in text_files:
            cls.cache[file_path] = file_path.read_text()

        logger.debug("Cached files", file_count=len(cls.cache))

    @classmethod
    def get_text(cls, path: Path) -> str:
        """Get cached file content by filename."""
        try:
            text_content = cls.cache[path]
        except KeyError:
            logger.warning(
                "Prompt file not found in cache; appending",
                path=path,
                available_files=list(cls.cache.keys()),
            )
            cls.cache[path] = path.read_text()
            return cls.get_text(path)

        return text_content
