from gptnt.cli.statics.app import statics_app
from gptnt.common.typer import LazyAsyncGroup


def main() -> None:
    """Run the CLI."""
    app = LazyAsyncGroup(name=None, help="GPTNT.", no_args_is_help=True)

    app.lazy_add(
        "throw",
        "gptnt.cli.throw",
        "throw",
        "Launch a full experiment throw: experiment manager, game rooms, and AI players.",
        rich_help_panel="Interactive",
        no_args_is_help=True,
    )
    app.lazy_add(
        "generate",
        "gptnt.cli.generate_experiment_specs",
        "generate_experiment_specs",
        "Generate experiment spec JSON files using Hydra configuration.",
        rich_help_panel="Interactive",
    )
    app.lazy_add(
        "submit",
        "gptnt.cli.send_experiments",
        "send_experiment_specs_to_em",
        "Send the experiment specs to the EM queue.",
        rich_help_panel="Interactive",
    )
    app.lazy_add(
        "status",
        "gptnt.cli.status",
        "check_experiment_completion",
        "Check which experiments exist on wandb and their current status.",
        rich_help_panel="Interactive",
    )
    app.lazy_add(
        "kill",
        "gptnt.cli.kill",
        "force_kill",
        "Force kill all game and player processes.",
        rich_help_panel="Interactive",
    )
    app.lazy_add(
        "cleanup-outputs",
        "gptnt.cli.cleanup",
        "cleanup_experiment_outputs",
        "Consolidate and cleanup experiment outputs and WandB runs in one go.",
        rich_help_panel="Interactive",
    )
    app.lazy_add(
        "models",
        "gptnt.cli.models",
        "print_models_table",
        "Print a Rich table of all available model configs.",
        rich_help_panel="Configs",
    )
    app.lazy_add(
        "build-db",
        "gptnt.cli.build_db",
        "build_metadata_database",
        "Build the local DuckDB experiment database from experiment JSON files.",
        rich_help_panel="Analysis",
    )
    app.lazy_add(
        "analyse",
        "gptnt.cli.streamlit",
        "run_streamlit_app",
        "Run the Streamlit app (using subprocess).",
        rich_help_panel="Analysis",
    )

    app.add_command(statics_app)
    app()


if __name__ == "__main__":
    main()
