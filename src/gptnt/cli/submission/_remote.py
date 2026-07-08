"""Create a pull request against gptnt/submissions to submit a run bundle to the leaderboard.

Requires either a GITHUB_TOKEN env var or the `gh` CLI to be authenticated.
PyGitHub handles all GitHub API calls; pygit2 handles all local git operations.
"""

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

try:  # noqa: WPS229
    import pygit2
    from github import Auth, Github
    from github.AuthenticatedUser import AuthenticatedUser
    from github.Repository import Repository as GhRepository
except ImportError as err:
    raise ImportError(
        "Missing dependencies for submission remote operations. "
        "Please install the 'github' and 'pygit2' packages by installing the `submission` extra with `uv sync --all-groups --all-extras`."
    ) from err


SUBMISSION_REPO_SLUG = "gptnt/submissions"
SUBMISSION_REPO_HTTPS = f"https://github.com/{SUBMISSION_REPO_SLUG}"


def _get_token() -> str:
    """Return a GitHub token.

    Prefers GITHUB_TOKEN env var. Falls back to `gh auth token` if gh is installed. Raises if
    neither is available.
    """
    if token := os.environ.get("GITHUB_TOKEN"):
        return token
    if shutil.which("gh"):
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


def _fork_and_clone(
    source: GhRepository,
    local_dir: Path,
    gh: Github,
    token: str,
    *,
    num_attempts_to_get_fork: int = 10,
) -> tuple[pygit2.Repository, str]:
    """Fork source, clone the fork into local_dir. Returns (pygit2 repo, login)."""
    user = gh.get_user()
    assert isinstance(user, AuthenticatedUser)
    fork = user.create_fork(source)

    # GitHub creates forks asynchronously — poll until refs are visible
    for _ in range(num_attempts_to_get_fork):
        try:
            _ = list(fork.get_branches())
        except Exception:  # noqa: BLE001 - We don't care why, we just want it to work.
            time.sleep(2)
        else:
            break

    return _clone(fork.clone_url, local_dir, token), user.login


def _create_and_checkout_branch(repo: pygit2.Repository, branch_name: str) -> None:
    branch = repo.create_branch(branch_name, repo.head.peel(type=pygit2.Commit), force=False)
    repo.checkout(branch)


def _stage_and_commit(
    repo: pygit2.Repository,
    rel_paths: list[str],
    message: str,
    author_name: str = "gptnt",
    author_email: str = "submissions@gptnt.com",
) -> None:
    # stage the commits
    index = repo.index
    index.read()
    for path in rel_paths:
        index.add(path)
    index.write()

    sig = pygit2.Signature(author_name, author_email)
    _ = repo.create_commit("HEAD", sig, sig, message, index.write_tree(), [repo.head.target])


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


def create_submission(  # noqa: WPS210
    *,
    slug: str = SUBMISSION_REPO_SLUG,
    submission_dir: Path,
    title: str | None = None,
    body: str | None = None,
) -> SubmissionResult:
    """Copy submission_dir/submissions/* into a clone/fork of slug and open a PR.

    Uses GITHUB_TOKEN env var if set, otherwise falls back to `gh auth token`.
    PyGitHub handles all GitHub API operations; pygit2 handles local git.
    """
    token = _get_token()
    gh = Github(auth=Auth.Token(token))
    source_repo = gh.get_repo(slug)

    branch_name = f"add-{submission_dir.resolve().name}"
    pr_title = title or f"Add submission: {submission_dir.name}"
    pr_body = body or ""

    with tempfile.TemporaryDirectory(prefix="gptnt-submission-clone-") as clone_dir:
        clone_dir_path = Path(clone_dir)
        if source_repo.permissions.push:
            local_repo = _clone(source_repo.clone_url, clone_dir_path, token)
            head = branch_name
        else:
            local_repo, login = _fork_and_clone(source_repo, clone_dir_path, gh, token)
            head = f"{login}:{branch_name}"

        _create_and_checkout_branch(local_repo, branch_name)

        rel_paths = _copy_submission(submission_dir, clone_dir_path)
        _stage_and_commit(local_repo, rel_paths, pr_title)
        _force_push(local_repo, branch_name, token)

        pr_url = _open_or_find_pr(source_repo=source_repo, head=head, title=pr_title, body=pr_body)

        return SubmissionResult(pr_url=pr_url, branch=branch_name)
