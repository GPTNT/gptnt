"""`gptnt submission validate`: check built bundles against their suite snapshots.

The doctor-style gate before a bundle goes to gptnt-submissions: the manifest parses (the schema
itself rejects unknown versions, tampered fingerprints, and blank identities), the submitter block
is filled in, the bundled suite snapshot matches its manifest and digest, every snapshot mission
is covered by exactly one valid run, and the payload players match the
manifest. Modified protected benchmark content fails validation. An unpinned statics dataset warns.
Interactive validation does not read live suite or mission configuration.

`gptnt submission new` bundles every recorded experiment for a (suite, model) group, so a retried
mission is reported here as a duplicate. Validate is the curation signal, not a bug in the build.
"""

import sys
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from rich.console import Console

from gptnt.cli.checks.formats import Report, ReportFormat
from gptnt.cli.checks.result import CheckResult
from gptnt.cli.submission._bundle import InteractiveBundle
from gptnt.cli.submission._checks import (
    check_mission_coverage,
    check_players,
    check_suite,
    load_bundle,
)
from gptnt.cli.submission._report import render_reports
from gptnt.common.paths import Paths

paths = Paths()
console = Console()


def validate_submission(
    path: Annotated[
        Path, Parameter(help="A bundle directory (holding submission.yaml) or a root to sweep.")
    ] = paths.submissions,
    *,
    report_format: Annotated[
        ReportFormat,
        Parameter(
            name="--format", help="rich (human), json (machine), or github (CI annotations)."
        ),
    ] = "rich",
) -> None:
    """Validate submission bundle(s).

    Any failed check exits non-zero (warnings never fail).
    """
    # A bundle dir matches itself because rglob's implicit `**` matches zero directories deep.
    bundle_dirs = [manifest.parent for manifest in path.rglob("submission.yaml")]
    if not bundle_dirs:
        raise RuntimeError(f"No bundles under {path}: nothing contains a submission.yaml.")

    reports = [
        Report(
            heading=str(bundle_dir if bundle_dir == path else bundle_dir.relative_to(path)),
            checks=_run_bundle_checks(bundle_dir),
        )
        for bundle_dir in bundle_dirs
    ]
    render_reports(reports, report_format, console)
    if any(report.failed for report in reports):
        sys.exit(1)


def _run_bundle_checks(bundle_dir: Path) -> list[CheckResult]:
    """Run every applicable check for one bundle.

    Empty sections simply don't render.
    """
    sections: list[CheckResult] = []

    loaded, structure_findings = load_bundle(bundle_dir)
    sections.extend(structure_findings)
    if loaded is None:
        return sections

    sections.extend(loaded.check_structure())
    sections.extend(loaded.check_submitter())

    if isinstance(loaded.bundle, InteractiveBundle):
        sections.extend(_interactive_sections(loaded.bundle))
    sections.extend(loaded.check_provenance())
    return sections


def _interactive_sections(bundle: InteractiveBundle) -> list[CheckResult]:
    """Return the suite-dependent sections.

    Coverage is meaningless against a wrong suite, so it skips.
    """
    suite_findings = check_suite(bundle)
    if any(finding.status == "fail" for finding in suite_findings):
        coverage_findings = [CheckResult.skipped("coverage", "suite checks failed; not assessed")]
    else:
        coverage_findings = check_mission_coverage(bundle, bundle.suite_lock.suites[0])
    return [*suite_findings, *coverage_findings, *check_players(bundle)]
