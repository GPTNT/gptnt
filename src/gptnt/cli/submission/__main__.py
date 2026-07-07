import anyio
from cyclopts import App

submission_app = App(name="submission", help="Build and check a submission for the leaderboard.")

submission_app.command(
    "gptnt.cli.submission.new:build_submission",
    name="new",
    help="Build submission bundles from the experiments DuckDB and statics outputs.",
)
# `validate` (and its GitHub Action gate in gptnt-submissions) is a follow-up; not wired yet.


def main() -> None:
    """Entry point for the `gptnt submission` command."""
    anyio.run(submission_app.run_async)


if __name__ == "__main__":
    main()
