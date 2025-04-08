from pathlib import Path

from pydantic_settings import BaseSettings


class Paths(BaseSettings):
    """Paths and locations for things."""

    root: Path = Path.cwd()

    configs: Path = root.joinpath("configs")
    storage: Path = root.joinpath("storage")

    logs: Path = storage.joinpath("logs")
    gradio_chats: Path = storage.joinpath("gradio_chats")
