from pathlib import Path

import pytest
from pytest_cases import param_fixture

from gptnt.ktane.game_settings import DEFAULT_PLAYER_SETTINGS_XML, KtanePlayerSettings


@pytest.fixture
def settings_instance() -> KtanePlayerSettings:
    return KtanePlayerSettings()


system = param_fixture("system", ["Windows", "Darwin", "Linux"])


def test_get_correct_path_for_system(settings_instance: KtanePlayerSettings, system: str) -> None:
    """Test that the correct settings path is returned based on the actual OS."""
    if system == "Windows":
        expected_path = settings_instance.windows
    elif system == "Darwin":
        expected_path = settings_instance.mac
    elif system == "Linux":
        expected_path = settings_instance.linux
    else:
        pytest.fail(f"Unsupported OS: {system}")

    assert settings_instance.get_settings_path(system=system) == expected_path


def test_settings_file_created_correctly_if_not_exist(
    settings_instance: KtanePlayerSettings, tmp_path: Path
) -> None:
    """Test that the settings file is created if one doesnt exist."""
    # Make the path for the output
    settings_path = tmp_path.joinpath("playerSettings.xml")

    # Make the file at our path
    settings_instance.create_settings_file(path=settings_path)

    assert settings_path.exists()
    assert settings_path.is_file()

    assert settings_path.read_text(encoding="utf-8").strip() == DEFAULT_PLAYER_SETTINGS_XML.strip()


def test_create_backup_settings_before_overwriting(
    settings_instance: KtanePlayerSettings, tmp_path: Path
) -> None:
    """Test that the settings file is backed up and then a new one is created."""
    # Make the path for the output
    settings_path = tmp_path.joinpath("playerSettings.xml")
    backup_path = settings_path.with_suffix(".bak")

    # Fill in the file with some content
    _ = settings_path.write_text("Some content", encoding="utf-8")
    assert settings_path.exists()
    assert settings_path.is_file()

    # Make the file at our path
    settings_instance.create_settings_file(path=settings_path)

    # Check that the backup file exists
    assert backup_path.exists()
    assert backup_path.is_file()
    assert backup_path.read_text(encoding="utf-8") == "Some content"

    # check the new file is the default
    assert settings_path.exists()
    assert settings_path.is_file()
    assert settings_path.read_text(encoding="utf-8").strip() == DEFAULT_PLAYER_SETTINGS_XML.strip()
