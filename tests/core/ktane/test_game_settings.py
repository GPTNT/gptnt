import os
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from pydantic import ValidationError
from pytest_cases import param_fixture, parametrize

from gptnt.ktane.game_settings import DEFAULT_PROGRESSION_XML, KtaneSettings


@pytest.fixture(autouse=True)
def clear_ktane_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate these tests from any `KTANE_*` vars in the ambient environment."""
    for key in list(os.environ):
        if key.startswith("KTANE_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def settings_instance() -> KtaneSettings:
    return KtaneSettings()


# Pin the baseline to explicit defaults: this runs at import time, before the
# autouse fixture clears the environment, so it must not read `KTANE_*` vars.
DEFAULT_PLAYER_SETTINGS_XML = KtaneSettings(
    music_volume=0, sfx_volume=0, language_code="en"
).rendered_player_settings


system = param_fixture("system", ["Windows", "Darwin", "Linux"])


def test_get_correct_path_for_system(settings_instance: KtaneSettings, system: str) -> None:
    """Test that the correct settings path is returned based on the actual OS."""
    if system == "Windows":
        expected_path = settings_instance.windows
    elif system == "Darwin":
        expected_path = settings_instance.mac
    elif system == "Linux":
        expected_path = settings_instance.linux
    else:
        pytest.fail(f"Unsupported OS: {system}")

    assert settings_instance.get_dir(system=system) == expected_path


@parametrize(
    ("file_name", "default_file_contents"),
    [
        ("playerSettings.xml", DEFAULT_PLAYER_SETTINGS_XML),
        ("progression.xml", DEFAULT_PROGRESSION_XML),
    ],
    ids=["playerSettings.xml", "progression.xml"],
)
def test_file_created_correctly_if_not_exist(
    settings_instance: KtaneSettings, tmp_path: Path, file_name: str, default_file_contents: str
) -> None:
    """Test that the file is created if one doesnt exist."""
    # Make the path for the output
    settings_path = tmp_path.joinpath(file_name)

    # Make the file at our path
    settings_instance.create_settings_files(dir_path=tmp_path)

    assert settings_path.exists()
    assert settings_path.is_file()
    assert settings_path.read_text() == default_file_contents


@parametrize(
    ("file_name", "default_file_contents"),
    [
        ("playerSettings.xml", DEFAULT_PLAYER_SETTINGS_XML),
        ("progression.xml", DEFAULT_PROGRESSION_XML),
    ],
    ids=["playerSettings.xml", "progression.xml"],
)
def test_create_backup_before_overwriting(
    settings_instance: KtaneSettings, tmp_path: Path, file_name: str, default_file_contents: str
) -> None:
    """Test that the file is backed up and then a new one is created."""
    # Make the path for the output
    settings_path = tmp_path.joinpath(file_name)

    # Fill in the file with some content
    _ = settings_path.write_text("Some content", encoding="utf-8")
    assert settings_path.exists()
    assert settings_path.is_file()

    # Make the file at our path
    settings_instance.create_settings_files(dir_path=tmp_path)

    # Check that the backup file exists
    backup_path = next(settings_path.parent.glob("*.bak"))
    assert backup_path.exists()
    assert backup_path.is_file()
    assert backup_path.read_text(encoding="utf-8") == "Some content"

    # check the new file is the default
    assert settings_path.exists()
    assert settings_path.is_file()
    assert settings_path.read_text() == default_file_contents


def _settings_element_text(rendered: str, tag: str) -> str | None:
    root = ET.fromstring(rendered)  # noqa: S314  # our own trusted template, not untrusted input
    return root.findtext(tag)


def test_rendered_player_settings_uses_configured_values() -> None:
    """Audio and a region-tagged language flow into the rendered playerSettings.xml."""
    settings = KtaneSettings(music_volume=40, sfx_volume=60, language_code="zh-CN")

    rendered = settings.rendered_player_settings

    assert _settings_element_text(rendered, "MusicVolume") == "40"
    assert _settings_element_text(rendered, "SFXVolume") == "60"
    assert _settings_element_text(rendered, "LanguageCode") == "zh-CN"


def test_rendered_player_settings_defaults_are_silent_english() -> None:
    """Defaults render muted audio and English, matching the shipped file."""
    rendered = KtaneSettings().rendered_player_settings

    assert _settings_element_text(rendered, "MusicVolume") == "0"
    assert _settings_element_text(rendered, "SFXVolume") == "0"
    assert _settings_element_text(rendered, "LanguageCode") == "en"


@parametrize("volume", [-1, 101])
def test_volume_out_of_range_is_rejected(volume: int) -> None:
    """Volumes outside 0-100 fail loudly rather than producing an invalid file."""
    with pytest.raises(ValidationError):
        _ = KtaneSettings(music_volume=volume)


@parametrize("code", ["", "xx", "en-GB", "fr&"])
def test_unsupported_language_code_is_rejected(code: str) -> None:
    """A code outside the KTANE set fails loudly instead of writing malformed XML."""
    with pytest.raises(ValidationError):
        _ = KtaneSettings(language_code=code)
