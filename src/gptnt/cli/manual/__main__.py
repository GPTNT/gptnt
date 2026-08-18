from cyclopts import App

manual_app = App(name="manual", help="Manage manual assets.")
manual_app.command(
    "gptnt.cli.manual.download:download",
    name="download",
    help="Download and cache the source assets required to build manuals.",
)
