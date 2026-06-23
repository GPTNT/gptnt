from cyclopts import App
from rich.console import Console

from gptnt.core.config import discover_experiments, discover_models, discover_providers

console = Console()

list_app = App(
    name="list", help="List the experiment presets and model configs a run.yaml can use."
)


def _print_names(title: str, names: list[str], *, empty_hint: str) -> None:
    """Print a titled, bulleted list of config names (or a hint when the directory is empty)."""
    if not names:
        console.print(f"[yellow]{empty_hint}[/yellow]")
        return
    console.print(f"[bold]{title}[/bold] ({len(names)})")
    for name in names:
        console.print(f"  {name}")


@list_app.command(name="experiments")
def list_experiments() -> None:
    """List the experiment presets under `configs/experiment/` (the `experiments:` field)."""
    _print_names(
        "Experiment presets",
        discover_experiments(),
        empty_hint="No experiment presets found under configs/experiment/.",
    )


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
