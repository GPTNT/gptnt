from gptnt.cli.experiments import check_experiments
from gptnt.cli.kill import force_kill
from gptnt.cli.models import print_models_table
from gptnt.cli.throw import throw
from gptnt.common.async_typer import AsyncTyper


def main() -> None:
    """Run the CLI."""
    app = AsyncTyper(
        help="GPTNT.", no_args_is_help=True, add_completion=False, rich_markup_mode="rich"
    )

    _ = app.command(name="kill", no_args_is_help=True)(force_kill)
    _ = app.command(name="models", no_args_is_help=True)(print_models_table)
    _ = app.command(name="throw", no_args_is_help=True)(throw)
    _ = app.command(name="status", no_args_is_help=False)(check_experiments)

    app()


if __name__ == "__main__":
    main()
