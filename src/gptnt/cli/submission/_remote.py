"""Open one pull request per model against gptnt/submissions to submit a run to the leaderboard.

Each top-level model directory under `submissions/` becomes its own branch, commit, and PR.
Requires either a GITHUB_TOKEN env var or the `gh` CLI to be authenticated. PyGitHub handles all
GitHub API calls; pygit2 handles all local git operations.
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


def _create_and_checkout_branch(
    repo: pygit2.Repository, branch_name: str, base: pygit2.Commit
) -> None:
    branch = repo.create_branch(branch_name, base)
    # Force so the working tree and index reset to `base`, dropping the previous model's files.
    repo.checkout(branch, strategy=pygit2.GIT_CHECKOUT_FORCE)


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


def _model_dirs(submission_dir: Path) -> list[Path]:
    """Every top-level model directory under submission_dir/submissions/, name-sorted.

    Each is one model (`<model-slug>_<capfp8>`), the boundary for one pull request.
    """
    src_root = submission_dir / "submissions"
    if not src_root.exists():
        raise ValueError(f"Expected a submissions/ directory inside {submission_dir}")
    model_dirs = sorted(path for path in src_root.iterdir() if path.is_dir())
    if not model_dirs:
        raise ValueError(f"No model submission directories found under {src_root}")
    return model_dirs


def _copy_model(model_dir: Path, submission_dir: Path, clone_dir: Path) -> list[str]:
    """Copy one model's subtree into clone_dir, keeping paths anchored at submission_dir.

    Returns repo-relative paths of the written files (for staging), each starting
    `submissions/<model>/...`.
    """
    rel_paths: list[str] = []
    for src_file in model_dir.rglob("*"):
        if not src_file.is_file():
            continue
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


def _push_and_open_pr(
    *,
    local_repo: pygit2.Repository,
    source_repo: GhRepository,
    branch_name: str,
    head: str,
    token: str,
    title: str,
    body: str,
) -> str:
    """Force-push one model's branch and open (or find) its PR, returning the PR URL."""
    _force_push(local_repo, branch_name, token)
    return _open_or_find_pr(source_repo=source_repo, head=head, title=title, body=body)


@dataclass
class SubmissionResult:
    model: str
    """The top-level model directory this pull request covers."""

    branch: str
    pr_url: str
    """The opened PR's URL, or `DRY_RUN_PR_URL` on a dry run."""

    error: str | None = None
    """Set when this model failed to push or open its PR."""


DRY_RUN_PR_URL = "(dry-run — no PR created)"


def _report_dry_run(
    *,
    model: str,
    branch: str,
    head: str,
    rel_paths: list[str],
    slug: str,
    base: str,
    title: str,
    body: str,
) -> None:
    """Print what a real run would push and open for one model, without touching GitHub."""
    tag = f"[yellow]DRY RUN [{model}][/yellow]"
    push_target = "your fork" if ":" in head else "the upstream repo (you have push access)"
    console.print(f"{tag}: would force-push branch {branch!r} to {push_target}")
    console.print(f"{tag}: would stage {len(rel_paths)} file(s):")
    for path in rel_paths:
        console.print(f"  - {path}")
    console.print(f"{tag}: would open PR {title!r} against {slug}@{base} (head {head})")
    if body:
        console.print(f"{tag}: PR body:\n{body}")


def create_submission(  # noqa: WPS210, WPS231
    *,
    slug: str = SUBMISSION_REPO_SLUG,
    submission_dir: Path,
    body: str | None = None,
    dry_run: bool = False,
) -> list[SubmissionResult]:
    """Open one pull request per model under submission_dir/submissions/.

    Each top-level model directory becomes its own branch, commit, and PR against `slug`. Auth,
    the repo lookup, and the clone/fork happen once, shared across every model. Uses GITHUB_TOKEN
    if set, otherwise `gh auth token`. PyGitHub handles the GitHub API; pygit2 handles local git.

    With `dry_run=True` every read-only step still runs (auth, repo lookup, clone, local commit)
    but nothing is mutated on GitHub — no fork, no push, no PR — so you can verify the flow.
    """
    token = _get_token()
    gh = Github(auth=Auth.Token(token))
    source_repo = gh.get_repo(slug)
    user = gh.get_user()
    assert isinstance(user, AuthenticatedUser)

    can_push = source_repo.permissions.push
    signature = _author_signature(user)
    pr_body = body or ""

    with tempfile.TemporaryDirectory(prefix="gptnt-submission-clone-") as clone_dir:
        clone_dir_path = Path(clone_dir)
        # A dry run never forks (that would mutate GitHub); it clones upstream read-only instead.
        if can_push or dry_run:
            local_repo = _clone(source_repo.clone_url, clone_dir_path, token)
        else:
            local_repo = _fork_and_clone(source_repo, clone_dir_path, user, token)
        base_commit = local_repo.head.peel(pygit2.Commit)

        outcomes: list[SubmissionResult] = []
        for model_dir in _model_dirs(submission_dir):
            branch_name = f"{user.login}/add-{model_dir.name}"
            head = branch_name if can_push else f"{user.login}:{branch_name}"
            pr_title = f"Add submission: {model_dir.name}"

            _create_and_checkout_branch(local_repo, branch_name, base_commit)
            rel_paths = _copy_model(model_dir, submission_dir, clone_dir_path)
            _stage_and_commit(local_repo, rel_paths, pr_title, signature=signature)

            if dry_run:
                _report_dry_run(
                    model=model_dir.name,
                    branch=branch_name,
                    head=head,
                    rel_paths=rel_paths,
                    slug=slug,
                    base=source_repo.default_branch,
                    title=pr_title,
                    body=pr_body,
                )
                outcomes.append(
                    SubmissionResult(
                        model=model_dir.name, branch=branch_name, pr_url=DRY_RUN_PR_URL
                    )
                )
                continue

            # Isolate one model so a single push/PR failure does not abort the rest of the batch.
            try:
                pr_url = _push_and_open_pr(
                    local_repo=local_repo,
                    source_repo=source_repo,
                    branch_name=branch_name,
                    head=head,
                    token=token,
                    title=pr_title,
                    body=pr_body,
                )
            except Exception as exc:  # noqa: BLE001 - capture per-model, report at the end.
                outcomes.append(
                    SubmissionResult(
                        model=model_dir.name, branch=branch_name, pr_url="", error=str(exc)
                    )
                )
            else:
                outcomes.append(
                    SubmissionResult(model=model_dir.name, branch=branch_name, pr_url=pr_url)
                )

        return outcomes
