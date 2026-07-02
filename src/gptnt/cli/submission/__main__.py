import anyio
from cyclopts import App

submission_app = App(
    name="submission", help="Build and check a submission bundle for the gptnt-submissions repo."
)

submission_app.command(
    "gptnt.cli.submission.new:build_submission",
    name="new",
    help="Build a submission bundle from local experiment outputs.",
)
submission_app.command(
    "gptnt.cli.submission.validate:validate_submission",
    name="validate",
    help="Check a submission bundle: deterministic consistency plus a score recompute.",
)


def main() -> None:
    """Entry point for the `gptnt submission` command."""
    anyio.run(submission_app.run_async)


if __name__ == "__main__":
    main()
