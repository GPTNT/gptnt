from gptnt.app.cli.launch import run_streamlit_app
from gptnt.core.common.typer import AsyncTyper
from gptnt.core.config import print_models_table
from gptnt.interactive.__main__ import interactive_app
from gptnt.records.cli.build_db import build_metadata_database
from gptnt.records.cli.cleanup import cleanup_experiment_outputs
from gptnt.records.cli.status import check_experiment_completion
from gptnt.records.cli.timing import query_span_timings
from gptnt.statics.cli.app import statics_app


def main() -> None:
    """Run the unified GPTNT CLI.

    This package owns the root `gptnt` command. It only assembles the command surface; every
    command's implementation lives in the package that owns its domain (interactive runtime,
    records data/analysis, app dashboard, statics evaluation, core configs). Each command keeps its
    heavy imports inside its function body so `gptnt --help` stays fast.
    """
    app = AsyncTyper(name=None, help="GPTNT.", no_args_is_help=True)

    # Interactive runtime (gptnt-interactive) — reuse its app's commands as top-level commands
    app.add_commands_from(interactive_app, rich_help_panel="Interactive")

    # Interactive analysis (gptnt-records) shown alongside the interactive commands
    _ = app.command("status", rich_help_panel="Interactive")(check_experiment_completion)
    _ = app.command("cleanup-outputs", rich_help_panel="Interactive")(cleanup_experiment_outputs)

    # Configs (gptnt-core)
    _ = app.command("models", rich_help_panel="Configs")(print_models_table)

    # Analysis (gptnt-records + gptnt-app)
    _ = app.command("build-db", rich_help_panel="Analysis")(build_metadata_database)
    _ = app.command("analyse", rich_help_panel="Analysis")(run_streamlit_app)
    _ = app.command("timing", rich_help_panel="Analysis")(query_span_timings)

    # Statics evaluation (gptnt-statics) — nested group
    app.add_typer(statics_app, rich_help_panel="Statics")
    app()


if __name__ == "__main__":
    main()
