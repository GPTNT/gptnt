from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from whenever import Instant

from gptnt.cli.models import PlayerSpec
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
    typer.Argument(
        help=r"Player specs as 'MODEL\[@PROVIDER]:COUNT' (repeatable)",
        parser=PlayerSpec.from_cli_string,
    ),
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
        "--interactive", "-i", help="Stream process logs to the terminal (like docker compose)"
    ),
]

LimitObservabilityOption = Annotated[
    bool, typer.Option("--limit-observability", help="Disable most instrumentation")
]


def _limit_observability_settings() -> dict[str, str]:
    """Severely limit instrumentation."""
    otel_resource_attributes = (
        f"{os.environ.get('OTEL_RESOURCE_ATTRIBUTES', '')},sampling.aggressive=true".strip(",")
    )
    return {
        "OBSERVABILITY_INSTRUMENT_FASTAPI": "false",
        "OBSERVABILITY_INSTRUMENT_FASTSTREAM": "false",
        "OBSERVABILITY_INSTRUMENT_HTTPX": "false",
        "OBSERVABILITY_INSTRUMENT_PYDANTIC_AI": "true",
        "OBSERVABILITY_INSTRUMENT_REDIS": "false",
        "OBSERVABILITY_ENABLE_METRICS": "false",
        "OBSERVABILITY_BYPASS_TAIL_SAMPLING": "false",
        "OTEL_RESOURCE_ATTRIBUTES": otel_resource_attributes,
    }


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
    limit_observability: LimitObservabilityOption = False,
) -> None:
    """Launch a full experiment throw: experiment manager, game rooms, and AI players.

    Orchestrates the full experiment pipeline by spinning up an experiment manager, the specified
    number of game rooms, and AI player processes. All processes are managed together and shut down
    cleanly on exit.

    [b][u]Player Specs:[/b][/u]
    Each player spec follows the format `MODEL@PROVIDER:COUNT`, where:

    - `MODEL`    - a model name matching a config in `configs/model/*.yaml`
    - `PROVIDER` - (optional) a provider override matching a config in
                   `configs/model/provider/*.yaml`
    - `COUNT`    - number of player processes to launch for this model (>= 1)

    If `@PROVIDER` is omitted, the model's default provider config is used. The `--players`
    argument can be repeated to run multiple model types simultaneously in the same throw.

    [b][u]Providers:[/b][/u]
    Providers are optional overrides that control which inference backend or API endpoint a
    model uses. Available providers are discovered automatically from
    `configs/model/provider/*.yaml`. If no provider is specified, the model falls back to its own
    default configuration.

    [b][u]Examples:[/b][/u]
    Launch the "big throw":
        gptnt throw 1 qwen3vl@vllm_box1:2 internvl35@vllm_box2:2 claude45:2 gemini-3:2

    Launch 4 rooms with 8 claude45 players using the default provider:
        gptnt throw 4 claude45:8

    [b][u]Notes:[/b][/u]
    - Total processes spawned = `1 (experiment manager) + rooms + total_players`.
    - Empty experiment recorder output directories from previous runs are cleaned up automatically
      before each throw.
    - Both `logs_dir` and `output_dir` are created automatically if they do not exist.
    - All processes share the `PYTHONUNBUFFERED=1` environment variable to ensure real-time log
      output.
    - Signal handling (e.g. `SIGINT`, `SIGTERM`) is managed automatically; all child processes
      are shut down gracefully on exit.
    """
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
    table.add_row("Limit observability:", "Yes" if limit_observability else "No")

    console.print()
    console.print(table)
    console.print()

    env_base: dict[str, str] = {"PYTHONUNBUFFERED": "1"}
    if limit_observability:
        env_base.update(_limit_observability_settings())
    if wandb_entity:
        env_base["WANDB_ENTITY"] = wandb_entity
    if wandb_project:
        env_base["WANDB_PROJECT"] = wandb_project

    orch = ProcessOrchestrator(
        logs_dir=logs_dir, output_dir=output_dir, env_base=env_base, interactive=interactive
    )

    async with handle_signals(orch):
        await run_throw(orch, rooms, players, display_num, output_dir)
