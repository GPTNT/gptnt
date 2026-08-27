from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from rich.console import Console

from gptnt.cli.checks.render import render_report
from gptnt.cli.checks.result import CheckResult
from gptnt.provenance import BenchmarkIntegrityError, check_benchmark_integrity

console = Console()
_PACKAGE_DIR = Path(__file__).resolve().parent

ForceOption = Annotated[
    bool,
    Parameter(
        name="--force",
        help=(
            "Continue despite failed policy and preflight checks. Execution may still fail when "
            "a required input or service is unavailable. Records without valid release "
            "provenance cannot be submitted."
        ),
    ),
]

_RESTORE_HINT = (
    "Restore protected content to the release, or use --force. Forced records cannot be submitted."
)
_RELEASE_HINT = (
    "Fetch or base this checkout on a reachable annotated GPTNT release tag "
    "(vMAJOR.MINOR.PATCH), or use --force."
)
_FORCED_HINT = "forced execution records no release provenance and cannot be submitted"


@dataclass(frozen=True, kw_only=True)
class BenchmarkDiagnosis:
    """Rendered benchmark findings and whether they block score-producing work."""

    findings: list[CheckResult]
    permitted_input_findings: list[CheckResult]
    failed: bool
    protected_content_modified: bool


def _unavailable_reference(error: Exception, *, force: bool) -> BenchmarkDiagnosis:
    """Classify a missing reference, re-raising unexpected Git failures unless forced."""
    if not force and not isinstance(error, BenchmarkIntegrityError):
        raise error
    finding = (
        CheckResult.warned("Reference", str(error), _FORCED_HINT)
        if force
        else CheckResult.failed("Reference", str(error), _RELEASE_HINT)
    )
    return BenchmarkDiagnosis(
        findings=[finding],
        permitted_input_findings=[],
        failed=not force,
        protected_content_modified=False,
    )


def _protected_content_finding(
    *, protected_paths: tuple[str, ...], force: bool
) -> tuple[CheckResult, bool]:
    """Build the protected-content row and whether it blocks score-producing work."""
    if not protected_paths:
        return CheckResult.passed("Protected content", "matches"), False

    detail = f"modified: {', '.join(protected_paths)}"
    if force:
        return CheckResult.warned("Protected content", detail, _RESTORE_HINT), False
    return CheckResult.failed("Protected content", detail, _RESTORE_HINT), True


def diagnose_benchmark_integrity(
    *, force: bool = False, render: bool = True
) -> BenchmarkDiagnosis:
    """Check the release baseline, render its state, and classify protected modifications."""
    # Establish the release identity before classifying changes in the checkout.
    try:
        integrity = check_benchmark_integrity(_PACKAGE_DIR)
    except Exception as error:  # noqa: BLE001  (forced diagnosis must survive Git read failures)
        diagnosis = _unavailable_reference(error, force=force)
    else:
        # Keep protected benchmark changes separate from permitted user inputs.
        protected_finding, failed = _protected_content_finding(
            protected_paths=integrity.protected_changes, force=force
        )

        diagnosis = BenchmarkDiagnosis(
            findings=[
                CheckResult.passed("Reference", integrity.release_tag),
                CheckResult.passed("Release commit", integrity.release_commit[:7]),
                CheckResult.passed(
                    "Release protected digest", integrity.release_protected_content_digest[:19]
                ),
                CheckResult.passed(
                    "Checkout protected digest", integrity.protected_content_digest[:19]
                ),
                protected_finding,
            ],
            permitted_input_findings=[
                CheckResult.passed("Changed inputs", ", ".join(integrity.permitted_input_changes))
            ]
            if integrity.permitted_input_changes
            else [],
            failed=failed,
            protected_content_modified=integrity.protected_content_modified,
        )

    # Let callers defer rendering when the diagnosis belongs in a larger command report.
    if render:
        render_benchmark_diagnosis(diagnosis)
    # Make forced modified-content execution visible whenever it changes the gate outcome.
    if force and diagnosis.protected_content_modified:
        console.print(
            "\n[bold yellow]WARNING: protected benchmark content is modified.[/bold yellow] "
            "Forced execution is enabled. Records will omit release provenance and cannot be "
            "submitted."
        )
    return diagnosis


def render_benchmark_diagnosis(diagnosis: BenchmarkDiagnosis) -> None:
    """Render benchmark identity and permitted input changes as separate sections."""
    render_report(
        console,
        {
            "Benchmark": diagnosis.findings,
            "Permitted input changes": diagnosis.permitted_input_findings,
        },
    )


def require_benchmark_integrity(*, force: bool = False) -> None:
    """Stop a score-producing command when benchmark integrity cannot be established."""
    diagnosis = diagnose_benchmark_integrity(force=force, render=False)
    if not diagnosis.failed:
        return

    render_benchmark_diagnosis(diagnosis)
    console.print(
        "\n[bold red]Benchmark integrity failed.[/bold red] Fix the Benchmark rows above."
    )
    sys.exit(1)
