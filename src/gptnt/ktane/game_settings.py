import os
import platform
from datetime import UTC, datetime
from pathlib import Path

import structlog
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger()

DEFAULT_PLAYER_SETTINGS_XML = Path(__file__).parent.joinpath("playerSettings.xml").read_text()


class KtaneGameSettings(BaseSettings):
    """Game settings for KTANE."""

    game_width: int = Field(default=512, description="Width of the game window")
    game_height: int = Field(default=512, description="Height of the game window")

    def update_environment_variables(self) -> None:
        """Set the environment variables for the game settings."""
        os.environ["GAME_WIDTH"] = str(self.game_width)
        os.environ["GAME_HEIGHT"] = str(self.game_height)


def get_default_windows_location() -> Path:
    """Get the default location for the playerSettings.xml file on Windows."""
    return Path(os.getenv("APPDATA", "")).parent.joinpath(
        "LocalLow", "Steel Crate Games", "Keep Talking and Nobody Explodes", "playerSettings.xml"
    )


def get_default_mac_location() -> Path:
    """Get the default location for the playerSettings.xml file on Mac."""
    return Path.home().joinpath(
        "Library",
        "Application Support",
        "com.steelcrategames.keeptalkingandnobodyexplodes",
        "playerSettings.xml",
    )


def get_default_linux_location() -> Path:
    """Get the default location for the playerSettings.xml file on Linux."""
    return Path.home().joinpath(
        ".config",
        "unity3d",
        "Steel Crate Games",
        "Keep Talking and Nobody Explodes",
        "playerSettings.xml",
    )


class KtanePlayerSettings(BaseSettings):
    """Configure the playerSettings.xml file for KTANE.

    Store locations for settings for each system, and handle the creation.
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="_", env_nested_max_split=1, env_prefix="PLAYER_SETTINGS_"
    )

    windows: Path = Field(default_factory=get_default_windows_location)
    mac: Path = Field(default_factory=get_default_mac_location)
    linux: Path = Field(default_factory=get_default_linux_location)

    def get_settings_path(self, *, system: str | None = None) -> Path:
        """Determine the path to the playerSettings.xml file based on the operating system."""
        system = system or platform.system()
        system = system.lower()

        switcher = {"windows": self.windows, "darwin": self.mac, "linux": self.linux}

        try:
            return switcher[system]
        except KeyError:
            raise OSError(f"Unsupported OS: {system}") from None

    def backup_old_settings(self, *, path: Path | None = None) -> None:
        """Backup the old settings if it exists."""
        settings_path = path or self.get_settings_path()

        if settings_path.exists() and settings_path.read_text() == DEFAULT_PLAYER_SETTINGS_XML:
            logger.debug("Settings file is already the default, no need to backup.")
            return

        if settings_path.exists():
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            backup_location = settings_path.with_suffix(f".{timestamp}.bak")
            logger.warning(
                f"Settings file already exists, we need to replace it to run things automatically. We are going to backup your settings at {backup_location}"
            )
            _ = backup_location.write_bytes(settings_path.read_bytes())

    def create_settings_file(self, *, path: Path | None = None) -> None:
        """Create the playerSettings.xml file if it doesn't exist.

        We also backup old settings just in case.
        """
        settings_path = path or self.get_settings_path()
        self.backup_old_settings(path=settings_path)

        # Make the dir if it doesn't exist
        settings_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the settings
        _ = settings_path.write_text(DEFAULT_PLAYER_SETTINGS_XML, encoding="utf-8")

        logger.info(f"Settings file created at {settings_path}")


if __name__ == "__main__":
    # This is just for testing the settings file
    settings = KtanePlayerSettings()
    settings.create_settings_file()
