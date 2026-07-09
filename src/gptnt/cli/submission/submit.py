"""`gptnt submission submit` — open a PR against gptnt-submissions with a built bundle.

The final step after `new` + `validate`: it copies the `submissions/` tree into a clone (or fork)
of the target repo and opens a pull request. Pass `--dry-run` to exercise everything locally —
auth, repo lookup, clone, and the local commit — while skipping every GitHub mutation (no fork, no
push, no PR), so you can confirm the flow works and see the branch, staged files, and PR title
before anything goes out.

Needs the `submission` extra (`uv sync --all-groups --all-extras`) and a GitHub token, via
`GITHUB_TOKEN` or an authenticated `gh` CLI.
"""

from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from rich.console import Console

from gptnt.cli.submission._remote import SUBMISSION_REPO_SLUG, create_submission
from gptnt.common.paths import Paths

paths = Paths()
console = Console()


def submit_submission(
    path: Annotated[
        Path, Parameter(help="Directory containing the submissions/ tree to submit.")
    ] = paths.output,
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
    """Open (or refresh) a pull request submitting the bundle under `path`."""
    submission_result = create_submission(slug=repo, submission_dir=path, dry_run=dry_run)
    if dry_run:
        console.print(
            f"[bold]Dry run complete[/bold] — branch would be {submission_result.branch}."
        )
    else:
        console.print(
            f"[bold]Submitted[/bold] on branch {submission_result.branch}: {submission_result.pr_url}"
        )
