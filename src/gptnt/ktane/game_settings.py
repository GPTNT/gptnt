import os
import platform
from pathlib import Path

import structlog
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger()

DEFAULT_PLAYER_SETTINGS_XML = """
<?xml version="1.0" encoding="utf-8"?>
<PlayerSettings xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <InvertTiltControls>false</InvertTiltControls>
    <TouchpadInvert>false</TouchpadInvert>
    <RumbleEnabled>true</RumbleEnabled>
    <MusicVolume>0</MusicVolume>
    <SFXVolume>100</SFXVolume>
    <AntiAliasing>4</AntiAliasing>
    <VRModeRequested>true</VRModeRequested>
    <SecondScreenMode>InteractiveManual</SecondScreenMode>
    <VSync>1</VSync>
    <AccessibilitySettings>
        <AccessibilityVeto>
        <ComponentTypeEnum>Empty</ComponentTypeEnum>
        <ComponentTypeEnum>Empty</ComponentTypeEnum>
        <ComponentTypeEnum>Empty</ComponentTypeEnum>
        </AccessibilityVeto>
        <UnlockAllMissions>false</UnlockAllMissions>
    </AccessibilitySettings>
    <UseModsAlways>true</UseModsAlways>
    <SkipTitleScreen>true</SkipTitleScreen>
    <UseParallelModLoading>false</UseParallelModLoading>
    <LockMouseToWindow>true</LockMouseToWindow>
    <ShowLeaderBoards>true</ShowLeaderBoards>
    <ShowScanline>true</ShowScanline>
    <ShowRotationUI>true</ShowRotationUI>
    <LanguageCode>en</LanguageCode>
</PlayerSettings>
"""


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

    def create_settings_file(self, *, path: Path | None = None) -> None:
        """Load or create the playerSettings.xml file and ensure settings are correct."""
        settings_path = path or self.get_settings_path()

        # Make a backup of the settings file if it already exists
        if settings_path.exists():
            backup_location = settings_path.with_suffix(".bak")
            logger.warning(
                f"Settings file already exists, we need to replace it to run things automatically. We are going to backup your settings at {backup_location}"
            )
            _ = backup_location.write_bytes(settings_path.read_bytes())

        # Make the dir if it doesn't exist
        settings_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the settings
        _ = settings_path.write_text(DEFAULT_PLAYER_SETTINGS_XML, encoding="utf-8")
