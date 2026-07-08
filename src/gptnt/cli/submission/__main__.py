import anyio
from cyclopts import App

submission_app = App(name="submission", help="Build and check a submission for the leaderboard.")

submission_app.command(
    "gptnt.cli.submission.new:build_submission",
    name="new",
    help="Build submission bundles from the experiments DuckDB and statics outputs.",
)
submission_app.command(
    "gptnt.cli.submission.validate:validate_submission",
    name="validate",
    help="Validate submission bundle(s) against the local gptnt checkout.",
)


def main() -> None:
    """Entry point for the `gptnt submission` command."""
    anyio.run(submission_app.run_async)


if __name__ == "__main__":
    main()
