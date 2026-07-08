"""`gptnt submission validate` — check built bundles against the local checkout.

The doctor-style gate before a bundle goes to gptnt-submissions: the manifest parses (the schema
itself rejects unknown versions, tampered fingerprints, and blank identities), the submitter block
is filled in, the declared suite exists here unchanged (digest recomputed from disk), every
mission is covered by exactly one valid run, and the payload players match the manifest. Hygiene
issues (a dirty tree at run time, an unpinned statics dataset) warn but never fail. It needs a
full gptnt checkout: the suite configs and mission sets are the reference the bundle is checked
against.

`gptnt submission new` bundles every recorded experiment for a (suite, model) group, so a retried
mission surfaces here as a duplicate — validate is the curation signal, not a bug in the build.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 — cyclopts resolves the command's type hints at runtime
from typing import TYPE_CHECKING, Annotated

from cyclopts import Parameter
from rich.console import Console

from gptnt.cli.doctor.checks import CheckResult
from gptnt.cli.doctor.render import render_report
from gptnt.cli.submission._bundle import InteractiveBundle
from gptnt.cli.submission._checks import LoadedBundle, load_bundle
from gptnt.cli.submission._interactive import load_suite
from gptnt.common.paths import Paths

if TYPE_CHECKING:
    from gptnt.experiments.suite import Suite

paths = Paths()
console = Console()

type SuiteCache = dict[str, tuple["Suite | None", str]]


def validate_submission(
    path: Annotated[
        Path, Parameter(help="A bundle directory (holding submission.yaml) or a root to sweep.")
    ] = paths.submissions,
) -> None:
    """Validate submission bundle(s); any failed check exits non-zero (warnings never fail)."""
    # A bundle dir matches itself: rglob's implicit `**` also matches zero directories deep.
    bundle_dirs = [manifest.parent for manifest in path.rglob("submission.yaml")]
    if not bundle_dirs:
        raise RuntimeError(f"No bundles under {path}: nothing contains a submission.yaml.")

    suite_cache: SuiteCache = {}
    failed = 0
    for bundle_dir in bundle_dirs:
        sections = _run_bundle_checks(bundle_dir, suite_cache)
        heading = bundle_dir if bundle_dir == path else bundle_dir.relative_to(path)
        console.print(f"[bold]{heading}[/bold]")
        render_report(console, sections)
        findings = [finding for section in sections.values() for finding in section]
        failed += any(finding.status == "fail" for finding in findings)

    total = len(bundle_dirs)
    console.print(
        f"Validated {total} bundle(s): {total - failed} ok, {failed} failed.", style="bold"
    )
    if failed:
        raise RuntimeError("Validation found problems; fix the rows above and re-validate.")


def _run_bundle_checks(bundle_dir: Path, suite_cache: SuiteCache) -> dict[str, list[CheckResult]]:
    """Run every applicable check for one bundle; empty sections simply don't render."""
    loaded, structure_findings = load_bundle(bundle_dir)
    if loaded is None:
        return {"Structure": structure_findings}

    suite_findings, coverage_findings = _run_suite_checks(loaded, suite_cache)
    return {
        "Structure": [*structure_findings, *loaded.check_structure()],
        "Submitter": loaded.check_submitter(),
        "Suite": suite_findings,
        "Mission coverage": coverage_findings,
        "Players": loaded.check_players(),
        "Provenance": loaded.check_provenance(),
    }


def _run_suite_checks(
    loaded: LoadedBundle, suite_cache: SuiteCache
) -> tuple[list[CheckResult], list[CheckResult]]:
    """The suite-dependent findings; coverage is meaningless against a wrong suite, so it skips."""
    if not isinstance(loaded.bundle, InteractiveBundle):
        return [], []
    suite, load_error = _load_suite_cached(loaded.bundle.manifest.measured.suite_name, suite_cache)
    suite_findings = loaded.check_suite(suite, load_error=load_error)
    suite_ok = suite is not None and all(finding.status != "fail" for finding in suite_findings)
    coverage_findings = (
        loaded.check_mission_coverage(suite)
        if suite is not None and suite_ok
        else [CheckResult.skipped("coverage", "suite checks failed; not assessed")]
    )
    return suite_findings, coverage_findings


def _load_suite_cached(suite_name: str, cache: SuiteCache) -> tuple[Suite | None, str]:
    """Load (and memoise) one suite; hydra composes via a global singleton, so stay serial."""
    if suite_name not in cache:
        try:
            cache[suite_name] = (load_suite(suite_name), "")
        except Exception as error:  # noqa: BLE001 — hydra/OmegaConf raise many kinds; report, don't crash
            cache[suite_name] = (None, str(error))
    return cache[suite_name]
