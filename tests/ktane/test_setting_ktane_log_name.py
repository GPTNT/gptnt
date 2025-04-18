from pathlib import Path

import pytest

from gptnt.ktane.executable import set_port_number_of_logfile


@pytest.fixture
def fake_ktane_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Provides a mock ktane config path."""
    config_path = tmp_path / "logConfig.xml"
    _ = config_path.write_text('<file value="logs/ktane.log"/>', encoding="utf-8")

    monkeypatch.setattr("gptnt.ktane.executable.paths", type("Paths", (), {"ktane": tmp_path}))

    return config_path


def test_set_port_number_of_logfile_replaces_and_restores(fake_ktane_path: Path) -> None:
    """Check the function updates and restores the config file properly."""
    port = "8086"
    generator = set_port_number_of_logfile(port)

    assert next(generator) is True
    modified_content = fake_ktane_path.read_text(encoding="utf-8")
    assert f"logs/ktane_{port}.log" in modified_content

    assert next(generator) is True
    restored_content = fake_ktane_path.read_text(encoding="utf-8")
    assert "logs/ktane.log" in restored_content


def test_set_port_number_of_logfile_raises_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Check that a missing file raises the expected error."""
    monkeypatch.setattr("gptnt.ktane.executable.paths", type("Paths", (), {"ktane": tmp_path}))

    generator = set_port_number_of_logfile("1234")
    with pytest.raises(FileNotFoundError):
        _ = next(generator)
