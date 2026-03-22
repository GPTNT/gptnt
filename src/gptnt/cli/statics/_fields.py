from typing import Annotated

import typer

from gptnt.cli.models import PlayerSpec

ModelOption = Annotated[
    PlayerSpec,
    typer.Option(
        "--model",
        help="Model as MODEL[@PROVIDER]. (see `gptnt models`)",
        parser=PlayerSpec.from_cli_string,
        rich_help_panel="Model",
    ),
]

DownloadOption = Annotated[
    bool,
    typer.Option(
        "--download", help="Download the dataset up-front before running (mainly for debugging)."
    ),
]

ThrowOption = Annotated[bool, typer.Option("--throw", help="Actually execute the evaluation.")]

UploadOption = Annotated[
    bool, typer.Option("--upload", help="Upload the evaluation results to Weave.")
]

LimitInstancesOption = Annotated[
    int | None,
    typer.Option(
        "--limit-instances", help="Limit the number of instances to evaluate (for debugging)."
    ),
]

AllowThinkingOption = Annotated[
    bool,
    typer.Option(
        "--allow-thinking/--no-thinking", help="Enable reasoning/thinking mode for the model."
    ),
]
