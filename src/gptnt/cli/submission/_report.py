"""Render `gptnt submission validate` results with submission's wording over `checks.formats`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gptnt.cli.checks.formats import Report, ReportFormat, render_reports as _render_reports

if TYPE_CHECKING:
    from rich.console import Console


def render_reports(reports: list[Report], report_format: ReportFormat, console: Console) -> None:
    """Emit every bundle's result in the requested format, with submission's wording."""
    _render_reports(reports, report_format, console, noun="bundle", title="Submission validation")
