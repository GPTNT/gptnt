"""`gptnt submission validate`: check submission bundles for internal consistency.

The doctor-style gate before a bundle goes to gptnt-submissions first parses the manifest. The
schema rejects unknown versions, tampered fingerprints, and blank identities. Validation then
checks the submitter block, suite snapshot, mission coverage, and payload players. Modified
protected benchmark content fails validation. An unpinned statics dataset warns. By default,
interactive validation reads only the bundled suite snapshot. `--require-installed-lock-match` also
requires that snapshot to exactly match the suite registry resolved by the running GPTNT
installation.

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
    check_installed_lock_match,
    check_installed_release_match,
    check_mission_coverage,
    check_players,
    check_suite,
    load_bundle,
)
from gptnt.cli.submission._report import render_reports
from gptnt.common.paths import Paths
from gptnt.experiments.suite.lock import SuiteLock, SuiteNotFrozenError

paths = Paths()
console = Console()
_PACKAGE_DIR = Path(__file__).resolve().parent

RequireInstalledLockMatchOption = Annotated[
    bool,
    Parameter(
        name="--require-installed-lock-match",
        help=(
            "Require each interactive bundle's suite snapshot to exactly match the suite registry "
            "shipped with this GPTNT installation."
        ),
    ),
]

RequireInstalledReleaseMatchOption = Annotated[
    bool,
    Parameter(
        name="--require-installed-release-match",
        help=(
            "Recompute protected content at each bundle's declared release and require its "
            "recorded release digest to match."
        ),
    ),
]


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
    require_installed_lock_match: RequireInstalledLockMatchOption = False,
    require_installed_release_match: RequireInstalledReleaseMatchOption = False,
) -> None:
    """Validate submission bundle(s).

    Any failed check exits non-zero (warnings never fail).
    """
    # A bundle dir matches itself because rglob's implicit `**` matches zero directories deep.
    bundle_dirs = [manifest.parent for manifest in path.rglob("submission.yaml")]
    if not bundle_dirs:
        raise RuntimeError(f"No bundles under {path}: nothing contains a submission.yaml.")

    installed_suite_registry = (
        _load_installed_suite_registry() if require_installed_lock_match else None
    )

    reports = [
        Report(
            heading=str(bundle_dir if bundle_dir == path else bundle_dir.relative_to(path)),
            checks=_run_bundle_checks(
                bundle_dir,
                installed_suite_registry=installed_suite_registry,
                require_installed_release_match=require_installed_release_match,
            ),
        )
        for bundle_dir in bundle_dirs
    ]
    render_reports(reports, report_format, console)
    if any(report.failed for report in reports):
        sys.exit(1)


def _load_installed_suite_registry() -> SuiteLock:
    """Return the suite registry resolved by this GPTNT installation."""
    try:
        return SuiteLock.from_lock_path()
    except SuiteNotFrozenError as error:
        raise RuntimeError(f"Installed GPTNT suite registry is unavailable: {error}") from error


def _run_bundle_checks(
    bundle_dir: Path,
    *,
    installed_suite_registry: SuiteLock | None,
    require_installed_release_match: bool,
) -> list[CheckResult]:
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
    if require_installed_release_match:
        sections.append(check_installed_release_match(loaded.manifest.provenance, _PACKAGE_DIR))

    if isinstance(loaded.bundle, InteractiveBundle):
        sections.extend(
            _interactive_sections(loaded.bundle, installed_suite_registry=installed_suite_registry)
        )
    sections.extend(loaded.check_provenance())
    return sections


def _interactive_sections(
    bundle: InteractiveBundle, *, installed_suite_registry: SuiteLock | None
) -> list[CheckResult]:
    """Return the suite-dependent sections.

    Coverage is meaningless against a wrong suite, so it skips.
    """
    suite_findings = check_suite(bundle)
    if any(finding.status == "fail" for finding in suite_findings):
        coverage_findings = [CheckResult.skipped("coverage", "suite checks failed; not assessed")]
    else:
        coverage_findings = check_mission_coverage(bundle, bundle.suite_lock.suites[0])
    installed_match = (
        [check_installed_lock_match(bundle, installed_suite_registry)]
        if installed_suite_registry
        else []
    )
    return [*suite_findings, *installed_match, *coverage_findings, *check_players(bundle)]
