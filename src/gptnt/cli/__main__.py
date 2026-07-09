import anyio
from cyclopts import App, Group

BACKEND = "asyncio"


def build_app() -> App:
    """Assemble the root `gptnt` command surface.

    This package owns the root `gptnt` command. It only assembles the command surface; every
    command's implementation lives in the package that owns its domain (interactive runtime,
    records data/analysis, app dashboard, statics evaluation, core configs).

    Every command is registered by lazy import-path string, so the command's module, and its heavy
    dependencies (hydra, torch, polars, duckdb, wandb, ...), is imported only when that command is
    invoked or when its own `--help` is shown.
    """
    app = App(name="gptnt", help="GPTNT.", backend=BACKEND)

    onboarding = Group("Onboarding", sort_key=0)
    interactive = Group("Interactive", sort_key=1)
    analysis = Group("Analysis", sort_key=2)
    statics = Group("Statics", sort_key=3)

    # Onboarding (gptnt-cli) — verify the system, then scaffold + validate your model.
    app.command(
        "gptnt.cli.doctor.command:doctor",
        name="doctor",
        group=onboarding,
        help="Check that this machine is ready to run the benchmark, and print fixes for what isn't.",
    )
    app.command(
        "gptnt.cli.player.new:new_app",
        name="new",
        group=onboarding,
        help="Scaffold new player/provider configs.",
    )
    app.command(
        "gptnt.cli.measure_tokens_per_image:measure_tokens_per_image",
        name="measure-tokens-per-image",
        group=onboarding,
        help="Measure a model's per-image token cost.",
    )
    app.command(
        "gptnt.cli.list_configs:list_app",
        name="list",
        group=onboarding,
        help="List the experiment presets and player configs a run.yaml can reference.",
    )
    app.command(
        "gptnt.cli.generate_specs:generate",
        name="generate",
        group=onboarding,
        help="Generate experiment specs from a run.yaml.",
    )
    app.command(
        "gptnt.cli.generate_missions:generate_missions",
        name="generate-missions",
        group=onboarding,
        help="Materialise a mission set into configs/missions/ from the seed-based generator.",
    )
    app.command(
        "gptnt.cli.suite.__main__:suite_app",
        name="suite",
        group=onboarding,
        help="Freeze and guard the suites.lock registry.",
    )
    app.command(
        "gptnt.cli.run.command:run",
        name="run",
        group=onboarding,
        help="Run a run.yaml's pre-generated specs end-to-end: doctor → spawn → submit → monitor.",
    )

    # Interactive runtime (gptnt-interactive) — flattened in as top-level commands.
    app.command(
        "gptnt.cli.interactive.submit:send_experiment_specs_to_em",
        name="submit",
        group=interactive,
        help="Send the experiment specs to the EM queue.",
    )
    app.command(
        "gptnt.cli.interactive.kill:force_kill",
        name="kill",
        group=interactive,
        help="Force kill all game and player processes.",
    )
    app.command(
        "gptnt.cli.experiments.status:check_experiment_completion",
        name="status",
        group=interactive,
        help="Show which experiments are done, failed, running, or not yet attempted.",
    )
    app.command(
        "gptnt.cli.experiments.cleanup:cleanup_experiment_outputs",
        name="cleanup-outputs",
        group=interactive,
        help="Delete local experiment outputs that crashed or never completed, plus orphaned .tmp writes. Previews by default; pass --execute to delete.",
    )
    app.command(
        "gptnt.cli.experiments.cleanup_wandb:reconcile_wandb_runs",
        name="reconcile-wandb",
        group=interactive,
        help="Reconcile local outputs against W&B: tags invalid/duplicate/orphaned remote W&B runs as 'old' and deletes local files lacking a valid run. Mutates remote W&B state. Previews by default; pass --execute to apply.",
    )

    # Analysis (gptnt-experiments + gptnt-app).
    app.command(
        "gptnt.cli.experiments.build_db:build_metadata_database",
        name="build-db",
        group=analysis,
        help="Build the local DuckDB experiment database from experiment JSON files.",
    )
    app.command(
        "gptnt.cli.analysis.launch:run_streamlit_app",
        name="analyse",
        group=analysis,
        help="Run the Streamlit analysis app.",
    )
    app.command(
        "gptnt.cli.experiments.timing:query_span_timings",
        name="timing",
        group=analysis,
        help="Summarise LLM inference time vs framework overhead for an experiment run.",
    )
    app.command(
        "gptnt.cli.experiments.results:show_results",
        name="results",
        group=analysis,
        help="List completed experiment outcomes from the DuckDB results.",
    )

    # Statics evaluation (gptnt-statics) — nested group.
    app.command(
        "gptnt.cli.statics.__main__:statics_app",
        name="statics",
        group=statics,
        help="Run static evaluations against HuggingFace datasets.",
    )
    return app


def main() -> None:
    """Entry point for the `gptnt` command."""
    anyio.run(build_app().run_async, backend=BACKEND)


if __name__ == "__main__":
    main()
