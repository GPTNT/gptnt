from pathlib import Path

from pydantic_settings import BaseSettings


class Paths(BaseSettings):
    """Paths and locations for things."""

    root: Path = Path.cwd()

    configs: Path = root.joinpath("configs")
    storage: Path = root.joinpath("storage")
    output: Path = storage.joinpath("outputs")

    experiments: Path = storage.joinpath("experiments")
    test_experiments: Path = storage.joinpath("test_experiments")

    logs: Path = storage.joinpath("logs")
    gradio_chats: Path = output.joinpath("gradio_chats")

    ktane: Path = storage.joinpath("ktane")
    """Path to the where we store the game."""
