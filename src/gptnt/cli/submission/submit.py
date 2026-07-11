"""`gptnt submission submit` — open one PR per bundle against gptnt-submissions.

The final step after `new` + `validate`: for each bundle directory under `submissions/`, it copies
that bundle's subtree into a clone (or fork) of the target repo and opens a pull request. Pass
`--dry-run` to run everything locally — auth, repo lookup, clone, and the local commits — while
skipping every GitHub mutation (no fork, no push, no PR), so you can confirm the flow and see each
bundle's branch, staged files, and PR title before anything goes out.

Needs the `submission` extra (`uv sync --all-groups --extra submission`) and a GitHub token, via
`GITHUB_TOKEN` or an authenticated `gh` CLI.
"""

from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from rich.console import Console

from gptnt.common.paths import SUBMISSION_REPO_SLUG, Paths

paths = Paths()
console = Console()


def submit_submission(
    path: Annotated[
        Path, Parameter(help="Directory of submission bundles to submit.")
    ] = paths.submissions,
    *,
    repo: Annotated[
        str, Parameter(name="--repo", help="Target repo slug (owner/name).")
    ] = SUBMISSION_REPO_SLUG,
    dry_run: Annotated[
        bool,
        Parameter(
            name="--dry-run",
            help="Do everything locally but make no GitHub changes (no fork, push, or PR).",
        ),
    ] = False,
) -> None:
    """Open (or refresh) one pull request per bundle under `path`."""
    from gptnt.cli.submission._remote import create_submission  # noqa: PLC0415

    outcomes = create_submission(slug=repo, submission_dir=path, dry_run=dry_run)
    if dry_run:
        console.print(f"[bold]Dry run complete[/bold] — {len(outcomes)} PR(s) would be opened:")
        for outcome in outcomes:
            console.print(f"  - {outcome.bundle}: {outcome.branch}")
        return

    failed = 0
    for outcome in outcomes:
        if outcome.error is None:
            console.print(f"  - {outcome.bundle}: {outcome.pr_url}")
        else:
            failed += 1
            console.print(f"  - [red]{outcome.bundle}: {outcome.error}[/red]")

    console.print(f"[bold]Submitted[/bold] {len(outcomes) - failed}/{len(outcomes)} bundle(s).")
    if failed:
        raise RuntimeError(f"{failed} bundle(s) failed to submit; see above.")
