"""`gptnt submission validate` — check built bundles against the frozen `suites.lock`.

The doctor-style gate before a bundle goes to gptnt-submissions: the manifest parses (the schema
itself rejects unknown versions, tampered fingerprints, and blank identities), the submitter block
is filled in, the declared suite revision is frozen in the lock with a matching digest, every
mission the lock records is covered by exactly one valid run, and the payload players match the
manifest. Hygiene issues (a dirty tree at run time, an unpinned statics dataset) warn but never
fail. Its reference is `suites.lock`, which ships in the wheel, so it needs no live configs.

`gptnt submission new` bundles every recorded experiment for a (suite, model) group, so a retried
mission surfaces here as a duplicate — validate is the curation signal, not a bug in the build.
"""

import sys
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from rich.console import Console

from gptnt.cli.check_result import CheckResult
from gptnt.cli.submission._bundle import InteractiveBundle
from gptnt.cli.submission._checks import (
    check_mission_coverage,
    check_players,
    check_suite,
    load_bundle,
)
from gptnt.cli.submission._report import BundleReport, ReportFormat, render_reports
from gptnt.common.paths import Paths
from gptnt.experiments.suite.lock import SuiteLock, SuiteLockEntry, SuiteNotFrozenError

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
    """Validate submission bundle(s); any failed check exits non-zero (warnings never fail)."""
    # A bundle dir matches itself: rglob's implicit `**` also matches zero directories deep.
    bundle_dirs = [manifest.parent for manifest in path.rglob("submission.yaml")]
    if not bundle_dirs:
        raise RuntimeError(f"No bundles under {path}: nothing contains a submission.yaml.")

    lock = SuiteLock.from_lock_path()
    reports = [
        BundleReport(
            heading=str(bundle_dir if bundle_dir == path else bundle_dir.relative_to(path)),
            checks=_run_bundle_checks(bundle_dir, lock),
        )
        for bundle_dir in bundle_dirs
    ]
    render_reports(reports, report_format, console)
    if any(report.failed for report in reports):
        sys.exit(1)


def _run_bundle_checks(bundle_dir: Path, lock: SuiteLock) -> list[CheckResult]:
    """Run every applicable check for one bundle; empty sections simply don't render."""
    sections: list[CheckResult] = []

    loaded, structure_findings = load_bundle(bundle_dir)
    sections.extend(structure_findings)
    if loaded is None:
        return sections

    sections.extend(loaded.check_structure())
    sections.extend(loaded.check_submitter())

    if isinstance(loaded.bundle, InteractiveBundle):
        sections.extend(_interactive_sections(loaded.bundle, lock))
    sections.extend(loaded.check_provenance())
    return sections


def _interactive_sections(bundle: InteractiveBundle, lock: SuiteLock) -> list[CheckResult]:
    """The suite-dependent sections; coverage is meaningless against a wrong suite, so it skips."""
    measured = bundle.manifest.measured
    entry, lookup_error = _lookup_entry(lock, measured.suite_name, measured.suite_revision)
    suite_findings = check_suite(bundle, entry, lookup_error=lookup_error)
    if entry is None or any(finding.status == "fail" for finding in suite_findings):
        coverage_findings = [CheckResult.skipped("coverage", "suite checks failed; not assessed")]
    else:
        coverage_findings = check_mission_coverage(bundle, entry)
    return [*suite_findings, *coverage_findings, *check_players(bundle)]


def _lookup_entry(
    lock: SuiteLock, suite_name: str, suite_revision: int
) -> tuple[SuiteLockEntry | None, str]:
    """The lock entry for this exact `(name, revision)`, or `None` and why it isn't frozen."""
    try:
        return lock.select_entry(suite_name, suite_revision), ""
    except SuiteNotFrozenError as error:
        return None, str(error)
