from gptnt.cli.kill import force_kill
from gptnt.cli.models import print_models_table
from gptnt.cli.throw import throw
from gptnt.common.async_typer import AsyncTyper


def main() -> None:
    """Run the CLI."""
    app = AsyncTyper(help="GPTNT.", no_args_is_help=True, add_completion=False)

    _ = app.command(name="kill", no_args_is_help=True)(force_kill)
    _ = app.command(name="models", no_args_is_help=True)(print_models_table)
    _ = app.command(name="throw", no_args_is_help=True)(throw)

    app()


if __name__ == "__main__":
    main()
