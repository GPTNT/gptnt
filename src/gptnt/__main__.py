import structlog
from rich.console import Console

from gptnt.cli.build_db import build_metadata_database
from gptnt.cli.cleanup import cleanup_experiment_outputs
from gptnt.cli.generate_experiment_specs import generate_experiment_specs
from gptnt.cli.kill import force_kill
from gptnt.cli.models import print_models_table
from gptnt.cli.send_experiments import send_experiment_specs_to_em
from gptnt.cli.status import check_experiment_completion
from gptnt.cli.streamlit import run_streamlit_app
from gptnt.cli.throw import throw
from gptnt.common.async_typer import AsyncTyper

logger = structlog.get_logger()
console = Console()


def main() -> None:
    """Run the CLI."""
    app = AsyncTyper(
        help="GPTNT.", no_args_is_help=True, add_completion=False, rich_markup_mode="rich"
    )
    _ = app.command(name="throw", no_args_is_help=True, rich_help_panel="Interactive")(throw)
    _ = app.command(name="generate", rich_help_panel="Interactive")(generate_experiment_specs)
    _ = app.command(name="submit", rich_help_panel="Interactive")(send_experiment_specs_to_em)
    _ = app.command(name="status", rich_help_panel="Interactive")(check_experiment_completion)
    _ = app.command(name="kill", rich_help_panel="Interactive")(force_kill)
    _ = app.command(name="cleanup-outputs", rich_help_panel="Interactive")(
        cleanup_experiment_outputs
    )

    _ = app.command(name="models", no_args_is_help=True, rich_help_panel="Configs")(
        print_models_table
    )

    _ = app.command(name="build-db", rich_help_panel="Analysis")(build_metadata_database)
    _ = app.command(name="analyse", rich_help_panel="Analysis")(run_streamlit_app)

    app()


if __name__ == "__main__":
    main()
