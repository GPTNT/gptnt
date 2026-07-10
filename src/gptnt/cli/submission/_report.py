"""Rendering `gptnt submission validate` results in the format the caller asked for.

`rich` is the human default (doctor's tables). `json` and `github` are for CI: `json` is a
machine-readable summary, `github` emits workflow annotations for each failure or warning plus a
job-summary table.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from gptnt.cli.doctor.render import render_report

if TYPE_CHECKING:
    from rich.console import Console

    from gptnt.cli.check_result import CheckResult, CheckStatus

ReportFormat = Literal["rich", "json", "github"]

_STATUS_GLYPH: dict[str, str] = {"pass": "✓", "fail": "✗", "warn": "⚠", "skip": "⊘"}


def _emit(console: Console, text: str) -> None:
    """Print one line verbatim: no rich markup, highlighting, or wrapping to corrupt CI output."""
    console.print(text, markup=False, highlight=False, soft_wrap=True)


@dataclass(frozen=True)
class BundleReport:
    """One bundle's heading and the checks it produced."""

    heading: str
    checks: list[CheckResult]

    @property
    def failed(self) -> bool:
        """True if any check failed (warnings and skips never fail the run)."""
        return any(check.status == "fail" for check in self.checks)


def render_reports(
    reports: list[BundleReport], report_format: ReportFormat, console: Console
) -> None:
    """Emit every bundle's result in the requested format."""
    if report_format == "json":
        _render_json(reports, console)
    elif report_format == "github":
        _render_github(reports, console)
    else:
        _render_rich(reports, console)


def _tally(reports: list[BundleReport]) -> tuple[int, int]:
    """`(total, failed)` bundle counts."""
    return len(reports), sum(report.failed for report in reports)


def _render_rich(reports: list[BundleReport], console: Console) -> None:
    """Doctor's per-section tables, one heading per bundle, then a one-line tally."""
    for report in reports:
        render_report(console, {report.heading: report.checks})
    total, failed = _tally(reports)
    console.print(
        f"Validated {total} bundle(s): {total - failed} ok, {failed} failed.", style="bold"
    )


def _render_json(reports: list[BundleReport], console: Console) -> None:
    """A machine-readable summary plus every check, for a CI step to parse."""
    total, failed = _tally(reports)
    payload = {
        "summary": {"total": total, "ok": total - failed, "failed": failed},
        "bundles": [
            {
                "bundle": report.heading,
                "ok": not report.failed,
                "checks": [
                    {
                        "name": check.name,
                        "status": check.status,
                        "detail": check.detail,
                        "hint": check.hint,
                    }
                    for check in report.checks
                ],
            }
            for report in reports
        ],
    }
    _emit(console, json.dumps(payload, indent=2))


def _render_github(reports: list[BundleReport], console: Console) -> None:
    """A workflow annotation per failure/warning, plus a job-summary table when running in CI."""
    for report in reports:
        for check in report.checks:
            if check.status in {"fail", "warn"}:
                _emit(console, _annotation(report.heading, check))
    _write_step_summary(reports)


def _annotation(heading: str, check: CheckResult) -> str:
    """One `::error`/`::warning` workflow command carrying the finding and its fix hint."""
    level = "error" if check.status == "fail" else "warning"
    title = _escape_property(f"{heading} · {check.name}")
    message = _escape_data(" — ".join(part for part in (check.detail, check.hint) if part))
    return f"::{level} title={title}::{message}"


def _write_step_summary(reports: list[BundleReport]) -> None:
    """Append a markdown table to the job summary, or do nothing outside a GitHub runner."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path is None:
        return
    total, failed = _tally(reports)
    lines = [f"## Submission validation — {total - failed}/{total} bundle(s) ok", ""]
    for report in reports:
        lines.append(f"### {'❌' if report.failed else '✅'} {report.heading}")
        lines += ["", "| | check | detail |", "| --- | --- | --- |"]
        lines += [_summary_row(check) for check in report.checks]
        lines.append("")
    body = "\n".join(lines)
    with Path(summary_path).open("a") as summary_file:
        _ = summary_file.write(f"{body}\n")


def _summary_row(check: CheckResult) -> str:
    """One markdown table row, with the cell-breaking pipe neutralised."""
    detail = " ".join(part for part in (check.detail, check.hint) if part).replace("|", r"\|")
    return f"| {_glyph(check.status)} | {check.name} | {detail} |"


def _glyph(status: CheckStatus) -> str:
    return _STATUS_GLYPH[status]


# GitHub workflow-command escaping: data and property values must escape these characters so the
# runner parses the whole message. https://docs.github.com/actions/reference/workflow-commands
def _escape_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    return _escape_data(text).replace(":", "%3A").replace(",", "%2C")
