"""Rendering for findings: the section-table renderer and doctor's model-matrix table."""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from collections.abc import Mapping

    from rich.console import Console, RenderableType

    from gptnt.cli.checks.players import PlayerDetail, PlayerReport
    from gptnt.cli.checks.result import CheckResult, CheckStatus

_GLYPHS: dict[str, tuple[str, str]] = {
    "pass": ("✓", "green"),
    "fail": ("✗", "bold red"),
    "warn": ("⚠", "yellow"),
    "skip": ("⊘", "dim"),
}

# Used to derive section-level border colour from worst finding.
_SEVERITY: dict[str, int] = {"skip": 0, "pass": 1, "warn": 2, "fail": 3}
_BORDER: dict[int, str] = {0: "dim", 1: "dim", 2: "yellow", 3: "red"}

_MESSAGE_CAP = 200


def _short(message: str | None) -> str:
    """Collapse whitespace and cap a (possibly multi-line, hydra-wrapped) message for a table."""
    if not message:
        return ""
    return textwrap.shorten(message, width=_MESSAGE_CAP, placeholder="…")


def _cell(status: CheckStatus) -> Text:
    glyph, style = _GLYPHS[status]
    return Text(glyph, style=style)


def _worst(findings: list[CheckResult]) -> int:
    return max((_SEVERITY[finding.status] for finding in findings), default=0)


def render_players(console: Console, details: list[PlayerDetail]) -> None:
    """Print one row per model: the exists/instantiates/live boxes plus every resolved field.

    This is the one model presentation for `gptnt doctor`; `--model` only narrows the set, so the
    same detail shows for every config — nothing is gated behind a flag.
    """
    if not details:
        console.print(
            Panel(
                "[bold red]No player configs found[/bold red] under configs/player/ — scaffold one "
                "with [bold]gptnt new player <name>[/bold].",
                title="[bold]Players[/bold]",
                border_style="red",
                padding=(0, 1),
            )
        )
        return

    notes = [_row_note(detail.report) for detail in details]
    has_notes = any(notes)

    table = Table(box=box.SIMPLE_HEAD, padding=(0, 1))
    table.add_column("Config", style="bold", no_wrap=True)
    table.add_column("Exists", justify="center", no_wrap=True)
    table.add_column("Inst.", justify="center", no_wrap=True)
    table.add_column("Live", justify="center", no_wrap=True)
    table.add_column("Resolved model", no_wrap=True)
    table.add_column("Player", no_wrap=True)
    table.add_column("Thinking", no_wrap=True)
    table.add_column("Structured", no_wrap=True)
    table.add_column("Interaction", no_wrap=True)
    if has_notes:  # only when something failed/warned — keep the happy-path table narrow
        table.add_column("Notes", overflow="fold", style="dim")

    for detail, note in zip(details, notes, strict=True):
        cells = _player_row(detail)
        if has_notes:
            cells.append(note)
        table.add_row(*cells)
    console.print(
        Panel(
            table,
            title="[bold]Players[/bold]",
            title_align="left",
            border_style="dim",
            padding=(0, 1),
        )
    )


def _player_row(detail: PlayerDetail) -> list[RenderableType]:
    """One model's cells: label, the three boxes, and the resolved fields (no Notes cell)."""
    report = detail.report
    caps = detail.static.capabilities
    if caps:
        fields = [
            detail.static.resolved_model_name or "—",
            caps.player_name,
            caps.thinking_method,
            str(caps.structured_output_mode),
            caps.interaction_location_method,
        ]
    else:  # did not compose/instantiate far enough to resolve any field
        fields = ["—", "—", "—", "—", "—"]

    return [
        report.label,
        _cell(report.exists),
        _cell(report.instantiates),
        _cell(report.live),
        *fields,
    ]


def _row_note(report: PlayerReport) -> str:
    """The Notes cell: blank for a clean pass, else the box message (error / cred / latency)."""
    clean = report.exists == "pass" and report.instantiates == "pass" and report.live == "skip"
    return "" if clean else _short(report.note)


def _section_table(findings: list[CheckResult]) -> Table:
    """Build the findings table for one section, adding a Fix column only when hints exist."""
    has_hints = any(finding.hint for finding in findings)

    table = Table(box=box.SIMPLE_HEAD, padding=(0, 1))
    table.add_column("", width=1, no_wrap=True)
    table.add_column("Check", style="bold", no_wrap=True)
    table.add_column("Detail", overflow="fold")
    if has_hints:
        table.add_column("Fix", style="dim", overflow="fold", max_width=45)

    for finding in findings:
        row_style = "dim" if finding.status == "skip" else ""
        row = [_cell(finding.status), finding.name, _short(finding.detail)]
        if has_hints:
            row.append(finding.hint)
        table.add_row(*row, style=row_style)
    return table


def render_report(console: Console, sections: Mapping[str, list[CheckResult]]) -> None:
    """Print one bordered panel per non-empty section."""
    for title, findings in sections.items():
        if not findings:
            continue

        border_style = _BORDER[_worst(findings)]
        console.print(
            Panel(
                _section_table(findings),
                title=f"[bold]{title}[/bold]",
                title_align="left",
                border_style=border_style,
                padding=(0, 1),
            )
        )
