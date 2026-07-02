import re
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter
from rich.console import Console

from gptnt.cli.player.templates import PLAYER_TEMPLATE, PROVIDER_TEMPLATE
from gptnt.common.paths import Paths

console = Console()
paths = Paths()

new_app = App(name="new", help="Scaffold new player/provider configs.")


def _validate_name(type_: type, name: str) -> None:  # noqa: ARG001
    """Reject empty, whitespace-y or path-traversing names (cyclopts parameter validator)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError(
            f"invalid name {name!r}: use only letters, digits, '-' and '_' "
            "(no spaces, slashes or '..')."
        )


NameArgument = Annotated[
    str,
    Parameter(
        help="Name for the config (letters, digits, '-' and '_' only).", validator=_validate_name
    ),
]


def _write_template(target: Path, template: str) -> None:
    """Write a template to the target path."""
    if target.exists():
        rel = target.relative_to(paths.configs.parent)
        raise FileExistsError(f"Config already exists: {rel} (delete it first to regenerate).")

    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(template)

    rel = target.relative_to(paths.configs.parent)
    console.print(f"[bold green]Created config:[/bold green] {rel}")


@new_app.command(name="player")
def new_player(name: NameArgument) -> None:
    """Scaffold a new player config at `configs/player/<name>.yaml`."""
    target = paths.configs / "player" / f"{name}.yaml"
    _write_template(target, PLAYER_TEMPLATE.replace("<NAME>", name))
    console.print(
        f"Next: validate it with [bold]gptnt doctor[/bold] ({name} is now discoverable)."
    )


@new_app.command(name="provider")
def new_provider(name: NameArgument) -> None:
    """Scaffold a new provider config at `configs/player/provider/<name>.yaml`."""
    target = paths.configs / "player" / "provider" / f"{name}.yaml"
    _write_template(target, PROVIDER_TEMPLATE.replace("<NAME>", name))
