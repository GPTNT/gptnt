"""Emit findings as rich tables, a JSON summary, or GitHub workflow annotations."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from gptnt.cli.checks.render import render_report

if TYPE_CHECKING:
    from rich.console import Console

    from gptnt.cli.checks.result import CheckResult

ReportFormat = Literal["rich", "json", "github"]

_STATUS_GLYPH: dict[str, str] = {"pass": "✓", "fail": "✗", "warn": "⚠", "skip": "⊘"}


@dataclass(frozen=True)
class Report:
    """One heading and the checks it produced (e.g. one bundle, one machine, one suite set)."""

    heading: str
    checks: list[CheckResult]

    @property
    def failed(self) -> bool:
        """True if any check failed (warnings and skips never fail the run)."""
        return any(check.status == "fail" for check in self.checks)


def render_reports(
    reports: list[Report],
    report_format: ReportFormat,
    console: Console,
    *,
    noun: str = "report",
    title: str = "Validation",
) -> None:
    """Emit every report in the requested format.

    `noun` is the per-report unit shown in tallies and JSON keys ("bundle", "report"); `title`
    heads the GitHub job summary.
    """
    if report_format == "json":
        _render_json(reports, console, noun=noun)
    elif report_format == "github":
        _render_github(reports, console, title=title, noun=noun)
    else:
        _render_rich(reports, console, noun=noun)


def _render_rich(reports: list[Report], console: Console, *, noun: str) -> None:
    """The shared per-section tables, one heading per report, then a one-line tally."""
    for report in reports:
        render_report(console, {report.heading: report.checks})
    total = len(reports)
    failed = sum(report.failed for report in reports)
    console.print(
        f"Validated {total} {noun}(s): {total - failed} ok, {failed} failed.", style="bold"
    )


def _render_json(reports: list[Report], console: Console, *, noun: str) -> None:
    """A machine-readable summary plus every check, for a CI step to parse."""
    total = len(reports)
    failed = sum(report.failed for report in reports)
    payload = {
        "summary": {"total": total, "ok": total - failed, "failed": failed},
        f"{noun}s": [
            {
                noun: report.heading,
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
    # markup/highlight off + soft_wrap so rich never mangles the machine-readable output.
    console.print(json.dumps(payload, indent=2), markup=False, highlight=False, soft_wrap=True)


def _render_github(reports: list[Report], console: Console, *, title: str, noun: str) -> None:
    """A workflow annotation per failure/warning, plus a job-summary table when running in CI."""
    for report in reports:
        for check in report.checks:
            if check.status in {"fail", "warn"}:
                # markup/highlight off + soft_wrap so rich never mangles the workflow command.
                console.print(
                    _annotation(report.heading, check),
                    markup=False,
                    highlight=False,
                    soft_wrap=True,
                )
    _write_step_summary(reports, title=title, noun=noun)


def _annotation(heading: str, check: CheckResult) -> str:
    """One `::error`/`::warning` workflow command carrying the finding and its fix hint."""
    level = "error" if check.status == "fail" else "warning"
    annotation_title = _escape_property(f"{heading} · {check.name}")
    message = _escape_data(" — ".join(part for part in (check.detail, check.hint) if part))
    return f"::{level} title={annotation_title}::{message}"


def _write_step_summary(reports: list[Report], *, title: str, noun: str) -> None:
    """Append a markdown table to the job summary, or do nothing outside a GitHub runner."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path is None:
        return
    total = len(reports)
    failed = sum(report.failed for report in reports)
    lines = [f"## {title} — {total - failed}/{total} {noun}(s) ok", ""]
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
    return f"| {_STATUS_GLYPH[check.status]} | {check.name} | {detail} |"


def _escape_data(text: str) -> str:
    """Escape a workflow-command data value so the runner parses the whole message.

    https://docs.github.com/actions/reference/workflow-commands
    """
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    """Escape a workflow-command property value (stricter: also escapes `:` and `,`)."""
    return _escape_data(text).replace(":", "%3A").replace(",", "%2C")
