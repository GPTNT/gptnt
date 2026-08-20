"""Render and enforce benchmark integrity at CLI score-producing boundaries."""

from __future__ import annotations

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

AllowModifiedBenchmarkOption = Annotated[
    bool,
    Parameter(
        name="--allow-modified-benchmark",
        help=(
            "Allow execution with protected benchmark content that differs from the release, "
            "for GPTNT development only. Benchmark records from this checkout are marked "
            "protected_content_modified=true and cannot be submitted. Missing or ambiguous "
            "release identity still blocks the command."
        ),
    ),
]

_RESTORE_HINT = (
    "Restore protected content to the release, or, only while developing GPTNT, use "
    "--allow-modified-benchmark. Modified records cannot be submitted."
)
_RESTORE_ONLY_HINT = "Restore protected content to the release before continuing."
_RELEASE_HINT = (
    "Check out an exact annotated GPTNT release tag (vMAJOR.MINOR.PATCH) before producing "
    "benchmark results."
)


@dataclass(frozen=True, kw_only=True)
class BenchmarkDiagnosis:
    """Rendered benchmark findings and whether they block score-producing work."""

    findings: list[CheckResult]
    permitted_input_findings: list[CheckResult]
    failed: bool
    protected_content_modified: bool


def _protected_content_finding(
    *,
    protected_paths: tuple[str, ...],
    allow_modified_benchmark: bool,
    contributor_override_available: bool,
) -> tuple[CheckResult, bool]:
    """Build the protected-content row and whether it blocks score-producing work."""
    if not protected_paths:
        return CheckResult.passed("Protected content", "matches"), False

    detail = f"modified: {', '.join(protected_paths)}"
    restore_hint = _RESTORE_HINT if contributor_override_available else _RESTORE_ONLY_HINT
    if allow_modified_benchmark:
        return CheckResult.warned("Protected content", detail, restore_hint), False
    return CheckResult.failed("Protected content", detail, restore_hint), True


def diagnose_benchmark_integrity(
    *,
    allow_modified_benchmark: bool = False,
    contributor_override_available: bool = True,
    render: bool = True,
) -> BenchmarkDiagnosis:
    """Check the release baseline, render its state, and classify protected modifications."""
    # Establish the release identity before classifying changes in the checkout.
    try:
        integrity = check_benchmark_integrity(_PACKAGE_DIR)
    except BenchmarkIntegrityError as error:
        diagnosis = BenchmarkDiagnosis(
            findings=[CheckResult.failed("Reference", str(error), _RELEASE_HINT)],
            permitted_input_findings=[],
            failed=True,
            protected_content_modified=False,
        )
    else:
        # Keep protected benchmark changes separate from permitted user inputs.
        protected_paths = (*integrity.protected_changes, *integrity.untracked_protected_files)
        protected_finding, failed = _protected_content_finding(
            protected_paths=protected_paths,
            allow_modified_benchmark=allow_modified_benchmark,
            contributor_override_available=contributor_override_available,
        )

        diagnosis = BenchmarkDiagnosis(
            findings=[
                CheckResult.passed("Reference", integrity.release_tag),
                CheckResult.passed("Release commit", integrity.release_commit[:7]),
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
    # Make the contributor override visible whenever it changes the outcome of the gate.
    if allow_modified_benchmark and diagnosis.protected_content_modified:
        console.print(
            "\n[bold yellow]WARNING: protected benchmark content is modified.[/bold yellow] "
            "The contributor override is enabled. Records will be marked "
            "[bold]protected_content_modified=true[/bold] and cannot be submitted."
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


def require_benchmark_integrity(
    *, allow_modified_benchmark: bool = False, contributor_override_available: bool = True
) -> None:
    """Stop a score-producing command when benchmark integrity cannot be established."""
    diagnosis = diagnose_benchmark_integrity(
        allow_modified_benchmark=allow_modified_benchmark,
        contributor_override_available=contributor_override_available,
        render=False,
    )
    if not diagnosis.failed:
        return

    render_benchmark_diagnosis(diagnosis)
    console.print(
        "\n[bold red]Benchmark integrity failed.[/bold red] Fix the Benchmark rows above."
    )
    raise RuntimeError(
        "benchmark integrity failed; restore protected content or check out an exact release tag"
    )
