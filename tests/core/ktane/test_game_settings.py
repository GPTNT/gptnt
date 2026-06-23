from pathlib import Path

import pytest
from pytest_cases import param_fixture, parametrize

from gptnt.ktane.game_settings import (
    DEFAULT_PLAYER_SETTINGS_XML,
    DEFAULT_PROGRESSION_XML,
    KtaneSettings,
)


@pytest.fixture
def settings_instance() -> KtaneSettings:
    return KtaneSettings()


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
