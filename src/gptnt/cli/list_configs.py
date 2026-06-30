from cyclopts import App
from rich.console import Console

from gptnt.cli.config_discovery import discover_models, discover_providers, discover_suites

console = Console()

list_app = App(name="list", help="List the suites and model configs a run.yaml can use.")


def _print_names(title: str, names: list[str], *, empty_hint: str) -> None:
    """Print a titled, bulleted list of config names (or a hint when the directory is empty)."""
    if not names:
        console.print(f"[yellow]{empty_hint}[/yellow]")
        return
    console.print(f"[bold]{title}[/bold] ({len(names)})")
    for name in names:
        console.print(f"  {name}")


@list_app.command(name="suites")
def list_suites() -> None:
    """List the suites under `configs/suites/` (the `suites:` field)."""
    _print_names("Suites", discover_suites(), empty_hint="No suites found under configs/suites/.")


@list_app.command(name="models")
def list_models() -> None:
    """List the model and provider configs under `configs/model/` (the `players:` field)."""
    _print_names(
        "Models", discover_models(), empty_hint="No model configs found under configs/model/."
    )
    providers = discover_providers()
    if providers:
        console.print()
        _print_names("Providers", providers, empty_hint="")
