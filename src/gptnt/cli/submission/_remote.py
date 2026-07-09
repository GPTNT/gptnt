"""Create a pull request against gptnt/submissions to submit a run bundle to the leaderboard.

Requires either a GITHUB_TOKEN env var or the `gh` CLI to be authenticated.
PyGitHub handles all GitHub API calls; pygit2 handles all local git operations.
"""

import os
import shutil
import subprocess
import tempfile
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

try:  # noqa: WPS229
    import pygit2
    from github import Auth, Github
    from github.AuthenticatedUser import AuthenticatedUser
    from github.Repository import Repository as GhRepository
except ImportError as err:
    raise ImportError(
        "Missing dependencies for submission remote operations. "
        "Please install the 'pygithub' and 'pygit2' packages by installing the `submission` extra "
        "(e.g. `uv sync --all-groups --extra submission` or `uv sync --all-groups --all-extras`)."
    ) from err


SUBMISSION_REPO_SLUG = "gptnt/submissions"
SUBMISSION_REPO_HTTPS = f"https://github.com/{SUBMISSION_REPO_SLUG}"

console = Console()


def _get_token() -> str:
    """Return a GitHub token.

    Prefers GITHUB_TOKEN env var. Falls back to `gh auth token` if gh is installed. Raises if
    neither is available.
    """
    if token := os.environ.get("GITHUB_TOKEN"):
        return token
    if shutil.which("gh"):
        with suppress(subprocess.CalledProcessError):
            token = subprocess.check_output(["gh", "auth", "token"]).decode().strip()
            if token:
                return token
    raise RuntimeError(
        "No GitHub token available. Set the GITHUB_TOKEN environment variable "
        "or install and authenticate the GitHub CLI (`gh auth login`)."
    )


def _remote_callbacks(token: str) -> pygit2.RemoteCallbacks:
    return pygit2.RemoteCallbacks(credentials=pygit2.UserPass("x-access-token", token))


def _clone(clone_url: str, local_dir: Path, token: str) -> pygit2.Repository:
    return pygit2.clone_repository(clone_url, str(local_dir), callbacks=_remote_callbacks(token))


def _author_signature(user: AuthenticatedUser) -> pygit2.Signature:
    name = user.name or user.login  # name can be None if not set
    # GitHub's no-reply format for users with private email
    email = user.email or f"{user.id}+{user.login}@users.noreply.github.com"
    return pygit2.Signature(name, email)


def _fork_and_clone(
    source: GhRepository,
    local_dir: Path,
    user: AuthenticatedUser,
    token: str,
    *,
    num_attempts_to_get_fork: int = 10,
) -> pygit2.Repository:
    """Fork source, clone upstream into local_dir, and rewire origin to the fork."""
    # If a fork already exists, this will do nothing
    fork = user.create_fork(source)

    # GitHub creates forks asynchronously — poll until refs are visible
    for _ in range(num_attempts_to_get_fork):
        try:
            _ = list(fork.get_branches())
        except Exception:  # noqa: BLE001 - We don't care why, we just want it to work.
            time.sleep(2)
        else:
            break

    # Clone upstream (always current), NOT the fork
    local_repo = _clone(source.clone_url, local_dir, token)

    # Rewire origin so pushes go to the fork
    local_repo.remotes.set_url("origin", fork.clone_url)

    return local_repo


def _create_and_checkout_branch(repo: pygit2.Repository, branch_name: str) -> None:
    branch = repo.create_branch(branch_name, repo.head.peel(pygit2.Commit))
    repo.checkout(branch)


def _stage_and_commit(
    repo: pygit2.Repository, rel_paths: list[str], message: str, signature: pygit2.Signature
) -> None:
    # stage the files
    index = repo.index
    index.read()
    for path in rel_paths:
        index.add(path)
    index.write()

    # Make the commit
    _ = repo.create_commit(
        "HEAD", signature, signature, message, index.write_tree(), [repo.head.target]
    )


def _force_push(repo: pygit2.Repository, branch_name: str, token: str) -> None:
    # + prefix = force, so re-running update updates an existing branch/PR
    repo.remotes["origin"].push(
        [f"+refs/heads/{branch_name}:refs/heads/{branch_name}"], callbacks=_remote_callbacks(token)
    )


def _copy_submission(submission_dir: Path, clone_dir: Path) -> list[str]:
    """Copy everything under submission_dir/submissions/ into clone_dir/submissions/.

    Returns repo-relative paths of all written files (for staging).
    """
    src_root = submission_dir / "submissions"
    if not src_root.exists():
        raise ValueError(f"Expected a submissions/ directory inside {submission_dir}")

    rel_paths: list[str] = []
    for src_file in src_root.rglob("*"):
        if not src_file.is_file():
            continue
        # e.g. submissions/model-abc/...
        rel = src_file.relative_to(submission_dir)
        destination = clone_dir / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        _ = shutil.copy2(src_file, destination)
        rel_paths.append(str(rel))

    return rel_paths


def _open_or_find_pr(*, source_repo: GhRepository, head: str, title: str, body: str) -> str:
    """Create a PR against source_repo and return its URL.

    Idempotent: checks for an existing open PR on the branch first, since
    create_pull raises if one already exists and we don't want to fail on re-runs.

    head format:
      - same-repo push:  "branch-name"
      - fork:            "login:branch-name"
    get_pulls requires "owner:branch" even for same-repo, so we normalise.
    """
    # ensure the head has the author prepended
    head_filter = head if ":" in head else f"{source_repo.owner.login}:{head}"

    # See if there is an existing PR for the current author
    existing = list(source_repo.get_pulls(state="open", head=head_filter))

    if existing:
        return existing[0].html_url

    # Otherwise, create a new PR
    pr = source_repo.create_pull(
        title=title, body=body, base=source_repo.default_branch, head=head
    )
    return pr.html_url


@dataclass
class SubmissionResult:
    pr_url: str
    branch: str


DRY_RUN_PR_URL = "(dry-run — no PR created)"


def _report_dry_run(
    *, branch: str, head: str, rel_paths: list[str], slug: str, base: str, title: str, body: str
) -> None:
    """Print what a real run would push and open, without touching GitHub."""
    push_target = "your fork" if ":" in head else "the upstream repo (you have push access)"
    console.print(f"[yellow]DRY RUN[/yellow]: would force-push branch {branch!r} to {push_target}")
    console.print(f"[yellow]DRY RUN[/yellow]: would stage {len(rel_paths)} file(s):")
    for path in rel_paths:
        console.print(f"  - {path}")
    console.print(
        f"[yellow]DRY RUN[/yellow]: would open PR {title!r} against {slug}@{base} (head {head})"
    )
    if body:
        console.print(f"[yellow]DRY RUN[/yellow]: PR body:\n{body}")


def create_submission(  # noqa: WPS210, WPS231
    *,
    slug: str = SUBMISSION_REPO_SLUG,
    submission_dir: Path,
    title: str | None = None,
    body: str | None = None,
    dry_run: bool = False,
) -> SubmissionResult:
    """Copy submission_dir/submissions/* into a clone/fork of slug and open a PR.

    Uses GITHUB_TOKEN env var if set, otherwise falls back to `gh auth token`. PyGitHub handles all
    GitHub API operations; pygit2 handles local git.

    With `dry_run=True` every read-only step still runs (auth, repo lookup, clone, local commit)
    but nothing is mutated on GitHub — no fork, no push, no PR — so you can verify the flow works.
    """
    token = _get_token()
    gh = Github(auth=Auth.Token(token))
    source_repo = gh.get_repo(slug)
    user = gh.get_user()
    assert isinstance(user, AuthenticatedUser)

    can_push = source_repo.permissions.push
    branch_name = f"{user.login}/add-{submission_dir.resolve().name}"
    head = branch_name if can_push else f"{user.login}:{branch_name}"
    pr_title = title or f"Add submission: {submission_dir.name}"
    pr_body = body or ""

    with tempfile.TemporaryDirectory(prefix="gptnt-submission-clone-") as clone_dir:
        clone_dir_path = Path(clone_dir)
        # A dry run never forks (that would mutate GitHub); it clones upstream read-only instead.
        if can_push or dry_run:
            local_repo = _clone(source_repo.clone_url, clone_dir_path, token)
        else:
            local_repo = _fork_and_clone(source_repo, clone_dir_path, user, token)

        _create_and_checkout_branch(local_repo, branch_name)

        rel_paths = _copy_submission(submission_dir, clone_dir_path)
        _stage_and_commit(local_repo, rel_paths, pr_title, signature=_author_signature(user))

        if dry_run:
            _report_dry_run(
                branch=branch_name,
                head=head,
                rel_paths=rel_paths,
                slug=slug,
                base=source_repo.default_branch,
                title=pr_title,
                body=pr_body,
            )
            return SubmissionResult(pr_url=DRY_RUN_PR_URL, branch=branch_name)

        _force_push(local_repo, branch_name, token)
        pr_url = _open_or_find_pr(source_repo=source_repo, head=head, title=pr_title, body=pr_body)

        return SubmissionResult(pr_url=pr_url, branch=branch_name)
