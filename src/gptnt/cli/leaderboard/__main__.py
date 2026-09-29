"""Commands for producing website leaderboard artifacts."""

from cyclopts import App

leaderboard_app = App(name="leaderboard", help="Build leaderboard artifacts from submissions.")

leaderboard_app.command(
    "gptnt.cli.leaderboard.build:build_leaderboard",
    name="build",
    help="Aggregate eligible submission bundles into a website JSON artifact.",
)
