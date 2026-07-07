"""List completed experiment outcomes from the DuckDB results database."""

from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from gptnt.common.paths import Paths
from gptnt.experiments.db.read import load_experiment_summaries
from gptnt.experiments.models import ExperimentSummary

console = Console()
paths = Paths()


def _outcome(summary: ExperimentSummary) -> Text:
    """The outcome label for a valid run.

    `is_valid_outcome` guarantees a valid summary is exactly one of solved, struck out, or timed
    out, so these three branches are total for the rows we render.
    """
    if summary.is_solved:
        return Text("✅ solved", style="green")
    if summary.is_strike_out:
        return Text("✗ strikeout", style="red")
    return Text("⏱ timeout", style="yellow")


def _build_table(valid: list[ExperimentSummary], invalid: list[ExperimentSummary]) -> Table:
    """One understated row per completed mission, with invalid attempts named in the caption."""
    table = Table(
        title="KTANE experiment outcomes",
        box=box.SIMPLE,
        show_edge=False,
        pad_edge=False,
        title_style="bold",
        caption_style="dim",
    )
    table.add_column("#", justify="right", no_wrap=True)
    table.add_column("outcome", no_wrap=True)
    table.add_column("defuser", no_wrap=True)
    table.add_column("expert", no_wrap=True)
    table.add_column("comm", no_wrap=True)
    table.add_column("mission")

    ordered = sorted(
        valid,
        key=lambda summary: (
            summary.mission_key,
            summary.defuser_name,
            summary.communication_style,
        ),
    )
    for rank, summary in enumerate(ordered, start=1):
        expert = Text(summary.expert_name) if summary.expert_name else Text("solo", style="dim")
        table.add_row(
            str(rank),
            _outcome(summary),
            summary.defuser_name,
            expert,
            summary.communication_style,
            summary.mission_key,
        )

    if invalid:
        names = "  ".join(sorted(crashed.attempt_name for crashed in invalid))
        table.caption = f"invalid ({len(invalid)}): {names}"
    return table


def show_results(
    db_path: Annotated[
        Path, Parameter(help="Path to the experiments DuckDB database.")
    ] = paths.experiments_db,
) -> None:
    """List completed experiment outcomes from the DuckDB results database."""
    if not db_path.exists():
        console.print(
            f"[red]No experiments database at {db_path}.[/red] "
            "Run [bold]gptnt build-db <output-dir>[/bold] first."
        )
        raise RuntimeError(f"No experiments database at {db_path}.")

    summaries = load_experiment_summaries(db_path)
    if not summaries:
        console.print(f"[dim]No completed experiments in {db_path}.[/dim]")
        return

    valid = [summary for summary in summaries if summary.is_valid]
    invalid = [summary for summary in summaries if not summary.is_valid]
    console.print(_build_table(valid, invalid))
