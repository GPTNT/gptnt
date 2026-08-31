from gptnt.cli.checks.result import CheckResult
from gptnt.cli.run.manifest import RunManifest
from gptnt.experiments.spec import ExperimentSpec
from gptnt.experiments.suite.lock import SuiteLock, SuiteLockEntry, SuiteNotFrozenError

SUITE_SELECTION_CHECK = "Suite selection"


def _select_entries(manifest: RunManifest) -> list[SuiteLockEntry]:
    """Load the frozen entries requested by a run manifest."""
    lock = SuiteLock.from_lock_path()
    return [lock.select_entry(selector.name, selector.revision) for selector in manifest.suites]


def check_suite_selection(manifest: RunManifest, specs: list[ExperimentSpec]) -> CheckResult:
    """Require loaded specs to contain exactly the frozen suites selected by the manifest."""
    try:
        entries = _select_entries(manifest)
    except SuiteNotFrozenError as error:
        return CheckResult.failed(
            SUITE_SELECTION_CHECK,
            str(error),
            "select a frozen suite revision and regenerate the experiment specs",
        )

    expected = {(entry.name, entry.revision) for entry in entries}
    actual = {(spec.suite_name, spec.suite_revision) for spec in specs}
    unexpected = actual - expected
    missing = expected - actual
    if unexpected or missing:
        details = []
        if unexpected:
            rendered = ", ".join(f"{name}@{revision}" for name, revision in sorted(unexpected))
            details.append(f"unexpected: {rendered}")
        if missing:
            rendered = ", ".join(f"{name}@{revision}" for name, revision in sorted(missing))
            details.append(f"missing: {rendered}")
        return CheckResult.failed(
            SUITE_SELECTION_CHECK,
            "; ".join(details),
            "regenerate the experiment specs from this run manifest",
        )

    rendered = ", ".join(f"{name}@{revision}" for name, revision in sorted(expected))
    return CheckResult.passed(SUITE_SELECTION_CHECK, f"loaded specs match {rendered}")
