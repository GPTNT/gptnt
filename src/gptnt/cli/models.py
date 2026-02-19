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


def discover_providers() -> list[str]:
    """Return sorted list of available provider names from configs/model/provider/*.yaml."""
    provider_config_dir = MODEL_CONFIG_DIR / "provider"
    if not provider_config_dir.is_dir():
        return []
    return sorted(path.stem for path in provider_config_dir.glob("*.yaml"))


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
    provider: str | None
    count: int


AVAILABLE_MODELS = discover_models()
AVAILABLE_PROVIDERS = discover_providers()


def _split_spec(spec: str) -> tuple[str, str | None, str]:
    """Split 'MODEL[@PROVIDER]:COUNT' into (model_name, provider, count_str)."""
    if ":" not in spec:
        raise typer.BadParameter(
            f"Invalid player spec '{spec}'. Expected MODEL[@PROVIDER]:COUNT (e.g. claude45:3 or claude45@openai:3)."
        )
    last_colon = spec.rfind(":")
    model_provider_part, count_str = spec[:last_colon], spec[last_colon + 1 :]

    if "@" in model_provider_part:
        model_name, provider = model_provider_part.split("@", 1)
    else:
        model_name, provider = model_provider_part, None

    return model_name, provider, count_str


def _validate_model_name(model_name: str, spec: str) -> None:
    if not model_name:
        raise typer.BadParameter(f"Model name cannot be empty in spec '{spec}'.")


def _validate_model(model_name: str) -> None:
    if model_name not in AVAILABLE_MODELS:
        console.print(f"[red]Unknown model:[/red] '{model_name}'\n")
        print_models_table()
        raise typer.Exit(code=1)


def _validate_provider(provider: str | None, spec: str) -> None:
    if provider is None:
        return
    if not provider:
        raise typer.BadParameter(f"Provider name cannot be empty in spec '{spec}'.")
    if provider not in AVAILABLE_PROVIDERS:
        console.print(f"[red]Unknown provider:[/red] '{provider}'\n")
        available = ", ".join(AVAILABLE_PROVIDERS) or "(none found)"
        console.print(f"[dim]Available providers:[/dim] {available}")
        raise typer.Exit(code=1)


def _parse_count(count_str: str) -> int:
    try:
        count = int(count_str)
    except ValueError:
        raise typer.BadParameter(f"Count must be an integer, got '{count_str}'.") from None
    if count < 1:
        raise typer.BadParameter(f"Count must be >= 1, got {count}.")
    return count


def parse_player_spec(spec: str) -> PlayerSpec:
    """Parse a 'MODEL[@PROVIDER]:COUNT' string.

    Raises typer.BadParameter on errors.
    """
    model_name, provider, count_str = _split_spec(spec)
    _validate_model_name(model_name, spec)
    _validate_model(model_name)
    _validate_provider(provider, spec)
    count = _parse_count(count_str)
    return PlayerSpec(model_name=model_name, provider=provider, count=count)
