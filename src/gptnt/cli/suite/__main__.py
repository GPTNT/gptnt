from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter
from rich.console import Console
from whenever import Instant

from gptnt.cli.config_discovery import discover_suites
from gptnt.cli.doctor import render
from gptnt.cli.doctor.checks import CheckResult
from gptnt.experiments.provenance import git_sha, gptnt_version
from gptnt.experiments.suite.compose import compose_suite
from gptnt.experiments.suite.freeze import FreezeReport, FreezeStamp, SuiteFreezeOutcome
from gptnt.experiments.suite.lock import SuiteLock, SuiteNotFrozenError

console = Console()

suite_app = App(name="suite", help="Freeze and guard the suites.lock registry.")

CheckOption = Annotated[
    bool,
    Parameter(
        name="--check",
        help="Verify the lock is complete without writing; exit non-zero if any suite is unfrozen.",
    ),
]


@suite_app.command(name="freeze")
def freeze(*, check: CheckOption = False) -> None:
    """Record every live suite revision in `suites.lock`, or verify it is complete with `--check`.

    A suite whose digest changed without a `revision` bump, or whose missions collide on a
    `mission_key`, is an error and blocks the write. `--check` additionally fails when a live suite
    has no current-revision entry, so CI catches a lock that was never regenerated.
    """
    try:
        existing = SuiteLock.from_lock_path()
    except SuiteNotFrozenError:
        existing = None

    stamp = FreezeStamp(
        frozen_at=Instant.now().format_common_iso(),
        gptnt_version=gptnt_version(),
        git_sha=git_sha() or "",
    )
    report = FreezeReport.reconcile(
        [compose_suite(name) for name in discover_suites()], existing, stamp
    )

    rows = [_check_result(outcome, check=check) for outcome in report.outcomes]
    render.render_report(console, {"Suites": rows})

    if check:
        _finish_check(rows)
        return
    _finish_write(report, SuiteLock.default_location)


def _check_result(outcome: SuiteFreezeOutcome, *, check: bool) -> CheckResult:
    """Map a reconciliation outcome to a rendered check row.

    `append` is a pass when writing (freeze records it) but a fail under `--check` (the lock is
    missing an entry it should already carry).
    """
    name = f"{outcome.name} (rev {outcome.revision})"
    if outcome.action == "unchanged":
        return CheckResult(name, "pass", outcome.detail)
    if outcome.action == "digest_mismatch":
        hint = f"Bump `revision` in configs/suites/{outcome.name}.yaml, then re-freeze."
        return CheckResult(name, "fail", outcome.detail, hint)
    if outcome.action == "duplicate_keys":
        return CheckResult(name, "fail", outcome.detail, "Regenerate the mission set.")
    if check:
        return CheckResult(name, "fail", "not in suites.lock", "Run `gptnt suite freeze`.")
    return CheckResult(name, "pass", "froze new entry")


def _finish_check(rows: list[CheckResult]) -> None:
    """Fail loudly if any suite is unfrozen or mismatched; otherwise report all frozen."""
    if any(row.status == "fail" for row in rows):
        raise RuntimeError("suites.lock is out of date; run `gptnt suite freeze`.")
    console.print(f"[green]{len(rows)} suites, all frozen.[/green]")


def _finish_write(report: FreezeReport, lock_path: Path) -> None:
    """Write the appended lock, refusing when a suite changed without a revision bump."""
    if report.has_blocking_errors:
        raise RuntimeError("Refusing to write suites.lock; fix the rows above.")
    report.updated_lock.dump_to_path(lock_path)
    appended = sum(1 for outcome in report.outcomes if outcome.action == "append")
    console.print(
        f"[green]Froze {len(report.outcomes)} suites ({appended} new) → {lock_path}.[/green]"
    )
