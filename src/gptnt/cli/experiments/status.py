from collections import defaultdict
from pathlib import Path
from typing import Annotated

import httpx
from cyclopts import Parameter
from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from gptnt.cli.config_discovery import discover_suites
from gptnt.cli.experiments.models import ExperimentsSource, SourceOption
from gptnt.common.paths import Paths
from gptnt.common.runtime_settings import RuntimeSettings
from gptnt.experiments.generation.pipeline import generate_specs
from gptnt.experiments.ledger import ExperimentStatus, Source, resolve_ledger

console = Console()
paths = Paths()


STATUS_ICONS: dict[ExperimentStatus, str] = {
    "done": "✅",
    "running": "🔄",
    "failed": "❌",
    "not_attempted": "·",
}
STATUS_STYLES: dict[ExperimentStatus, str] = {
    "done": "green",
    "running": "cyan",
    "failed": "red",
    "not_attempted": "dim",
}
STATUS_LABELS: dict[ExperimentStatus, str] = {
    "done": "done",
    "running": "running",
    "failed": "failed",
    "not_attempted": "not attempted",
}
STATUS_SORT_ORDER: dict[ExperimentStatus, int] = {
    "not_attempted": 0,
    "done": 1,
    "failed": 2,
    "running": 3,
}

ExperimentsArgument = Annotated[
    list[str] | None,
    Parameter(
        help=(
            "Zero or more experiment sources."
            "Pass nothing to generate all; "
            "pass a directory path to load from disk; "
            "pass suite id(s) (e.g. single-pairwise-sync) to generate only those."
        )
    ),
]


def _attempt_names_for_suites(suite_names: list[str]) -> list[str]:
    """Generate (in-process) the expected attempt names for the given suite names."""
    attempt_names: list[str] = []
    for suite_name in suite_names:
        console.print(f"  Adding suite: [cyan]{suite_name}[/cyan]")
        specs = generate_specs([f"suites={suite_name}"])
        attempt_names.extend(spec.attempt_name for spec in specs)
    return attempt_names


def _load_attempt_names_from_dir(directory: Path) -> list[str]:
    """Load attempt names from a directory of JSON files."""
    return [path.stem for path in directory.glob("*.json")]


def _resolve_experiments(sources: list[ExperimentsSource]) -> list[str]:
    """Load or generate the expected attempt names based on parsed CLI sources."""
    if not sources:
        console.print("[dim]Generating experiments for all suites...[/dim]")
        return _attempt_names_for_suites(discover_suites())

    if any(src.kind == "dir" for src in sources):
        if len(sources) > 1:
            raise ValueError("Cannot mix a directory path with suite ids.")
        directory = Path(sources[0].raw)
        console.print(f"[dim]Loading experiments from {directory}[/dim]")
        return _load_attempt_names_from_dir(directory)

    names = [src.raw for src in sources]
    console.print(f"[dim]Generating experiments for: {', '.join(names)}[/dim]")
    return _attempt_names_for_suites(names)


def _live_running() -> set[str]:
    """The attempt names the local EM is currently running/queueing, best-effort.

    A live overlay so a benchmark run shows in-flight progress without W&B. If the EM is not up
    (the common case when just inspecting results), this returns nothing rather than failing.
    """
    try:
        response = httpx.get(f"{RuntimeSettings().em_base_url}/active", timeout=2)
    except Exception:  # noqa: BLE001 — the overlay is optional; absence of the EM is normal
        return set()
    if response.status_code != 200:  # noqa: PLR2004
        return set()
    payload = response.json()
    return {*payload.get("running", []), *payload.get("queued", [])}


def _sort_key(entry: tuple[str, ExperimentStatus]) -> tuple[int, str]:
    """Order rows by status bucket (not-attempted first), then name."""
    name, status = entry
    return (STATUS_SORT_ORDER[status], name)


def _render_table(statuses: dict[str, ExperimentStatus]) -> None:
    table = Table(box=box.SIMPLE, show_header=True, show_edge=False, pad_edge=False, expand=False)
    table.add_column("#", justify="right", no_wrap=True)
    table.add_column("Experiment", style="default", no_wrap=True)
    table.add_column("St", justify="center", no_wrap=True)

    ordered = sorted(statuses.items(), key=_sort_key)
    summary: dict[ExperimentStatus, int] = defaultdict(int)
    for idx, (name, status) in enumerate(ordered):
        summary[status] += 1
        style = STATUS_STYLES[status]
        table.add_row(
            str(idx + 1), Text(name, style=style), Text(STATUS_ICONS[status], justify="center")
        )

    console.print(table)
    _render_summary(summary, total=len(statuses))


def _render_summary(summary: dict[ExperimentStatus, int], total: int) -> None:
    line = Text("  ")
    first = True
    for status in ("done", "running", "failed", "not_attempted"):
        count = summary.get(status, 0)
        if not count:
            continue
        if not first:
            _ = line.append("    ", style="dim")
        _ = line.append(
            f"{STATUS_ICONS[status]} {count} {STATUS_LABELS[status]}", style=STATUS_STYLES[status]
        )
        first = False
    remaining = summary.get("failed", 0) + summary.get("not_attempted", 0)
    _ = line.append(f"  ({remaining} remaining / {total} total)", style="dim")
    console.print(line)
    console.print()


def check_experiment_completion(
    sources: ExperimentsArgument = None,
    *,
    source: SourceOption = Source.local,
    output_dir: Annotated[
        Path,
        Parameter(
            help="Where recorded outputs live, for the local completion check.",
            env_var="EXPERIMENT_RECORDER",
        ),
    ] = paths.experiment_recorder_dir,
) -> None:
    """Show which experiments are done, failed, running, or not yet attempted."""
    parsed = [ExperimentsSource.from_cli_string(token) for token in sources or []]
    console.print()

    expected = _resolve_experiments(parsed)
    if not expected:
        console.print("[red]No experiments found. Aborting.[/red]")
        raise RuntimeError("No experiments found.")
    console.print(f"  Loaded [bold]{len(expected)}[/bold] expected experiments.\n")

    ledger = resolve_ledger(source, output_dir=output_dir)
    statuses = ledger.status_for(expected)

    # Overlay the live, in-flight experiments from the EM (a source the on-disk view cannot see).
    for attempt_name in _live_running():
        if attempt_name in statuses:
            statuses[attempt_name] = "running"

    console.print(f"[bold]Completion source:[/bold] [cyan]{source.value}[/cyan]\n")
    _render_table(statuses)
