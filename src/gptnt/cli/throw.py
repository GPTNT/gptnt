from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from whenever import Instant

from gptnt.cli.models import PlayerSpec, parse_player_spec
from gptnt.cli.orchestrator import ProcessOrchestrator
from gptnt.cli.spawn import handle_signals, run_throw
from gptnt.common.paths import Paths, remove_empty_experiment_recorder_outputs

console = Console()
paths = Paths()


CURRENT_TIMESTAMP = Instant.now().py_datetime().strftime("%Y%m%d_%H%M%S")

DEFAULT_LOGS_DIR = paths.logs.joinpath(f"throw_{CURRENT_TIMESTAMP}/")
DEFAULT_OUTPUT_DIR = paths.experiment_recorder.joinpath(CURRENT_TIMESTAMP)


PlayerOption = Annotated[
    list[PlayerSpec],
    typer.Argument(help="Player specs as MODEL:COUNT (repeatable)", parser=parse_player_spec),
]


DisplayNumOption = Annotated[
    int,
    typer.Option(
        "--display-num",
        "-d",
        help="X-Server display number for game instances",
        hidden="linux" not in sys.platform,
    ),
]

LogsDirOption = Annotated[
    Path, typer.Option(help="Location for console log outputs", rich_help_panel="Outputs")
]

OutputDirOption = Annotated[
    Path, typer.Option(help="Location for experiment outputs", rich_help_panel="Outputs")
]

InteractiveOption = Annotated[
    bool,
    typer.Option(
        "--interactive",
        "-i",
        help="Stream process logs to the terminal with coloured prefixes (like docker compose)",
    ),
]


async def throw(  # noqa: WPS213
    *,
    rooms: Annotated[int, typer.Argument(help="Number of game rooms to start", min=1)],
    players: PlayerOption,
    display_num: DisplayNumOption = 3,
    interactive: InteractiveOption = False,
    wandb_entity: Annotated[
        str | None,
        typer.Option(
            "--wandb-entity",
            help="Wandb entity (user or team)",
            envvar="WANDB_ENTITY",
            rich_help_panel="WandB",
        ),
    ] = None,
    wandb_project: Annotated[
        str | None,
        typer.Option(
            "--wandb-project",
            help="Wandb project name",
            envvar="WANDB_PROJECT",
            rich_help_panel="WandB",
        ),
    ] = None,
    logs_dir: LogsDirOption = DEFAULT_LOGS_DIR,
    output_dir: OutputDirOption = DEFAULT_OUTPUT_DIR,
) -> None:
    """Launch a full experiment throw: experiment manager, game rooms, and AI players."""
    total_players = sum(player.count for player in players)

    # Timestamped directories
    remove_empty_experiment_recorder_outputs(paths.experiment_recorder)
    logs_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Summary
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(no_wrap=True)
    table.add_column(highlight=True)

    table.add_row("Rooms:", str(rooms))
    table.add_row("Display:", f":{display_num}")
    for player in players:
        table.add_row(f"Players ({player.model_name}):", str(player.count))
    table.add_row("Total processes:", str(1 + rooms + total_players))
    if wandb_entity:
        table.add_row("WANDB_ENTITY:", wandb_entity)
    if wandb_project:
        table.add_row("WANDB_PROJECT:", wandb_project)
    table.add_section()
    table.add_row("Logs dir", str(logs_dir))
    table.add_row("Output dir", str(output_dir))

    console.print()
    console.print(table)
    console.print()

    env_base: dict[str, str] = {"PYTHONUNBUFFERED": "1"}
    if wandb_entity:
        env_base["WANDB_ENTITY"] = wandb_entity
    if wandb_project:
        env_base["WANDB_PROJECT"] = wandb_project

    orch = ProcessOrchestrator(
        logs_dir=logs_dir, output_dir=output_dir, env_base=env_base, interactive=interactive
    )

    async with handle_signals(orch):
        await run_throw(orch, rooms, players, display_num, output_dir)
