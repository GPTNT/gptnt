"""Rendering `gptnt submission validate` results.

A thin, submission-flavoured adapter over the shared `gptnt.cli.checks.formats` machinery: it fixes
the wording ("bundle", "Submission validation") and re-exports the generic pieces under the names
the command layer expects. `rich` is the human default; `json`/`github` are for CI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gptnt.cli.checks.formats import (
    Report as BundleReport,
    ReportFormat,
    render_reports as _render_reports,
)

if TYPE_CHECKING:
    from rich.console import Console

__all__ = ["BundleReport", "ReportFormat", "render_reports"]


def render_reports(
    reports: list[BundleReport], report_format: ReportFormat, console: Console
) -> None:
    """Emit every bundle's result in the requested format, with submission's wording."""
    _render_reports(reports, report_format, console, noun="bundle", title="Submission validation")
