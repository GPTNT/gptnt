import anyio
from cyclopts import App

interactive_app = App(name="interactive", help="Interactive commands.")
interactive_app.command(
    "gptnt.interactive.cli.send_experiments:send_experiment_specs_to_em",
    name="submit",
    help="Send the experiment specs to the EM queue.",
)
interactive_app.command(
    "gptnt.interactive.cli.kill:force_kill",
    name="kill",
    help="Force kill all game and player processes.",
)


def main() -> None:
    """Entry point for the standalone `gptnt-interactive` command."""
    anyio.run(interactive_app.run_async)


if __name__ == "__main__":
    main()
