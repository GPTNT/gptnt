import os
import platform
from datetime import UTC, datetime
from pathlib import Path

import logfire
import structlog
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from gptnt.common.image_ops import ImageDimensions

logger = structlog.get_logger()

DEFAULT_PLAYER_SETTINGS_XML = Path(__file__).parent.joinpath("playerSettings.xml").read_text()
DEFAULT_PROGRESSION_XML = Path(__file__).parent.joinpath("progression.xml").read_text()


def get_default_windows_location() -> Path:
    """Get the default location for the playerSettings.xml file on Windows."""
    return Path(os.getenv("APPDATA", "")).parent.joinpath(
        "LocalLow", "Steel Crate Games", "Keep Talking and Nobody Explodes"
    )


def get_default_mac_location() -> Path:
    """Get the default location for the playerSettings.xml file on Mac."""
    return Path.home().joinpath(
        "Library", "Application Support", "com.steelcrategames.keeptalkingandnobodyexplodes"
    )


def get_default_linux_location() -> Path:
    """Get the default location for the playerSettings.xml file on Linux."""
    return Path.home().joinpath(
        ".config", "unity3d", "Steel Crate Games", "Keep Talking and Nobody Explodes"
    )


class KtaneSettings(BaseSettings):
    """Configure settings for KTANE."""

    model_config = SettingsConfigDict(
        env_nested_delimiter="_", env_nested_max_split=1, env_prefix="KTANE_"
    )

    player_settings_file_name: str = "playerSettings.xml"
    progression_file_name: str = "progression.xml"

    windows: Path = Field(default_factory=get_default_windows_location)
    mac: Path = Field(default_factory=get_default_mac_location)
    linux: Path = Field(default_factory=get_default_linux_location)

    game_width: int = Field(
        default=640, description="Width of the game window", alias="game_width"
    )
    game_height: int = Field(
        default=480, description="Height of the game window", alias="game_height"
    )
    game_speed: int = Field(default=1, description="Multipler for the game speed")

    @property
    def image_dimensions(self) -> ImageDimensions:
        """Get the image dimensions for the game."""
        return ImageDimensions(width=self.game_width, height=self.game_height)

    def update_environment_variables(self) -> None:
        """Set the environment variables for the game settings."""
        os.environ["GAME_WIDTH"] = str(self.game_width)
        os.environ["GAME_HEIGHT"] = str(self.game_height)

    def get_dir(self, *, system: str | None = None) -> Path:
        """Determine the path to the playerSettings.xml file based on the operating system."""
        system = system or platform.system()
        system = system.lower()

        switcher = {"windows": self.windows, "darwin": self.mac, "linux": self.linux}

        try:
            return switcher[system]
        except KeyError:
            raise OSError(f"Unsupported OS: {system}") from None

    def backup_old_file(self, *, file_path: Path, default_file_contents: str) -> None:
        """Backup the old settings if it exists."""
        if file_path.exists() and file_path.read_text() == default_file_contents:
            logger.debug(f"'{file_path.name}' file is already good, no need to backup.")
            return

        if file_path.exists():
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            backup_location = file_path.with_suffix(f".{timestamp}.bak")
            with logfire.suppress_instrumentation():
                logger.warning(
                    f"'{file_path.name} file already exists, we need to replace it to run things automatically. We are going to backup your settings at '{backup_location}'"
                )
            _ = backup_location.write_bytes(file_path.read_bytes())

    def create_file(self, *, file_path: Path, default_file_contents: str) -> None:
        """Create the file if it doesn't exist.

        We also backup old settings just in case.
        """
        self.backup_old_file(file_path=file_path, default_file_contents=default_file_contents)

        file_path.parent.mkdir(parents=True, exist_ok=True)
        _ = file_path.write_text(default_file_contents, encoding="utf-8")

        logger.info(f"File created at '{file_path}'")

    def create_player_settings_file(self, *, path: Path | None = None) -> None:
        """Create the playerSettings.xml file if it doesn't exist.

        We also backup old settings just in case.
        """
        player_settings_path = path or self.get_dir().joinpath(self.player_settings_file_name)
        self.create_file(
            file_path=player_settings_path, default_file_contents=DEFAULT_PLAYER_SETTINGS_XML
        )

    def create_progression_file(self, *, path: Path | None = None) -> None:
        """Create the progression.xml file if it doesn't exist.

        We also backup old settings just in case.
        """
        progression_path = path or self.get_dir().joinpath(self.progression_file_name)
        self.create_file(file_path=progression_path, default_file_contents=DEFAULT_PROGRESSION_XML)

    def create_settings_files(self, *, dir_path: Path | None = None) -> None:
        """Create the playerSettings.xml and progression.xml files if they don't exist.

        We also backup old settings just in case.
        """
        self.create_player_settings_file(
            path=dir_path.joinpath(self.player_settings_file_name) if dir_path else None
        )
        self.create_progression_file(
            path=dir_path.joinpath(self.progression_file_name) if dir_path else None
        )

        logger.info("Player settings files created successfully.")


if __name__ == "__main__":
    # This is just for testing the settings file
    settings = KtaneSettings()
    settings.create_settings_files()
