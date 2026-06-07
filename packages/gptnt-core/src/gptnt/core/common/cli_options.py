"""Shared CLI option/argument types reused across the gptnt command-line surface."""

from typing import Annotated

import typer

from gptnt.core.config import PlayerSpec

WandbEntityOption = Annotated[
    str,
    typer.Option(
        "--wandb-entity",
        help="WandB entity (user or team) name",
        envvar="WANDB_ENTITY",
        rich_help_panel="WandB",
    ),
]
WandbProjectOption = Annotated[
    str,
    typer.Option(
        "--wandb-project",
        help="WandB project name",
        envvar="WANDB_PROJECT",
        rich_help_panel="WandB",
    ),
]

PlayerOption = Annotated[
    list[PlayerSpec],
    typer.Argument(
        help=r"Player specs as 'MODEL\[@PROVIDER]\[:COUNT]' (repeatable)",
        parser=PlayerSpec.from_cli_string,
    ),
]
