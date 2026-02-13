from __future__ import annotations

from dataclasses import dataclass

import typer
from rich.console import Console
from rich.table import Table

from gptnt.common.paths import Paths

console = Console()
paths = Paths()

MODEL_CONFIG_DIR = paths.configs / "model"


def discover_models() -> list[str]:
    """Return sorted list of available model names from configs/model/*.yaml."""
    if not MODEL_CONFIG_DIR.is_dir():
        return []
    return sorted(path.stem for path in MODEL_CONFIG_DIR.glob("*.yaml"))


def print_models_table() -> None:
    """Print a Rich table of all available model configs."""
    models = discover_models()
    table = Table(title="Available Models", show_lines=False)
    table.add_column("Model Name", style="cyan")
    table.add_column("Config File", style="dim")
    for model_name in models:
        table.add_row(model_name, f"configs/model/{model_name}.yaml")
    console.print(table)


@dataclass
class PlayerSpec:
    """Parsed player specification."""

    model_name: str
    count: int


AVAILABLE_MODELS = discover_models()


def parse_player_spec(spec: str) -> PlayerSpec:  # noqa: WPS238
    """Parse a 'MODEL:COUNT' string.

    Raises typer.BadParameter on errors.
    """
    parts = spec.split(":")
    if len(parts) != 2:  # noqa: PLR2004
        raise typer.BadParameter(
            f"Invalid player spec '{spec}'. Expected MODEL:COUNT (e.g. claude45:3)."
        )
    model_name, count_str = parts
    if model_name not in AVAILABLE_MODELS:
        console.print(f"[red]Unknown model:[/red] '{model_name}'\n")
        print_models_table()
        raise typer.Exit(code=1)

    try:
        count = int(count_str)
    except ValueError:
        raise typer.BadParameter(f"Count must be an integer, got '{count_str}'.")  # noqa: B904
    if count < 1:
        raise typer.BadParameter(f"Count must be >= 1, got {count}.")
    return PlayerSpec(model_name=model_name, count=count)
