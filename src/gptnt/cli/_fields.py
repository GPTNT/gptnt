"""Shared CLI fields and options."""

from typing import Annotated

import typer

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
