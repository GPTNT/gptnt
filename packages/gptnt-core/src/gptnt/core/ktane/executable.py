import platform
from collections.abc import Generator
from pathlib import Path

from gptnt.core.common.paths import Paths


class GameNotFoundError(FileNotFoundError):
    """Exception for when the executable is not there."""


class ModNotFoundError(FileNotFoundError):
    """Exception for when the mod is not found in the game directory."""


paths = Paths()
MODS_DIR = paths.ktane.joinpath("mods")


def _get_executable(*, executable_suffix: str, needs_ktane_data_dir: bool) -> Path:
    """Retrieves the path to the executable."""
    # get the exe within the folder
    exe_path_list = list(paths.ktane.glob(executable_suffix))
    if not exe_path_list:
        raise GameNotFoundError(
            f"Executables not found in {paths.ktane}. Make sure you have the game copied into it."
        )
    if not len(exe_path_list) == 1:
        raise GameNotFoundError(
            f"There are too many `exe`'s within {paths.ktane}. There should only be one"
        )

    exe_path = exe_path_list[0]

    if needs_ktane_data_dir:
        ktane_data_path = exe_path.parent.joinpath("ktane_Data")
        # Make sure the ktane_data folder is there
        if not ktane_data_path.exists():
            raise GameNotFoundError(
                f"{ktane_data_path} not found at {paths.ktane}. This is needed to run the game"
            )

    return exe_path


def _get_mac_executable() -> Path:
    """Retrieves the path to the executable on macOS."""
    app_path = _get_executable(executable_suffix="*.app", needs_ktane_data_dir=False)
    app_executable_dir = app_path.joinpath("Contents/MacOS")
    try:
        app_executable_path = next(app_executable_dir.iterdir())
    except StopIteration as err:
        raise GameNotFoundError(
            f"Executable not found in {app_executable_dir}. The app may be corrupted."
        ) from err

    return app_executable_path


def get_executable_path() -> Path:
    """Retrieves the path to the executable."""
    if not paths.ktane.exists() or not paths.ktane.is_dir():
        raise GameNotFoundError(f"Game directory not found at {paths.ktane}.")

    system = platform.system()

    if system == "Windows":
        return _get_executable(executable_suffix="*.exe", needs_ktane_data_dir=True)

    if system == "Darwin":
        return _get_mac_executable()

    if system == "Linux":
        return _get_executable(executable_suffix="*.x86_64", needs_ktane_data_dir=True)

    raise RuntimeError(f"Unsupported operating system: {system}.")


def ensure_mod_exists() -> bool:
    """Ensures that the mod exists in the game directory."""
    if not MODS_DIR.exists() or not MODS_DIR.is_dir():
        raise ModNotFoundError(f"Mods directory not found at {MODS_DIR}.")

    mod_path = MODS_DIR.joinpath("Gptnt Plays")

    if not mod_path.exists():
        raise ModNotFoundError(f"Mod not found at {mod_path}.")

    return True


def set_port_number_of_logfile(port: str) -> Generator[bool]:
    """Sets the log name with the port number."""
    log_path = paths.ktane.joinpath("logConfig.xml")
    if not log_path.exists():
        raise FileNotFoundError(f"Log config file not found at {log_path}.")

    original_data = log_path.read_text(encoding="utf-8")

    updated_data = original_data.replace('"logs/ktane.log"/', f'"logs/ktane_{port}.log"/')

    _ = log_path.write_text(data=updated_data, encoding="utf-8")
    yield True

    _ = log_path.write_text(data=original_data, encoding="utf-8")
    yield True
