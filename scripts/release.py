"""Cut a gptnt release.

gptnt versions are 4-segment `EDITION.MAJOR.MINOR.PATCH`:

- **EDITION** is human-driven. Bump it with `--new-edition` when a change makes eval results no
  longer comparable with prior editions (resets MAJOR.MINOR.PATCH to `0.0.0`).
- **MAJOR.MINOR.PATCH** is derived automatically from the Conventional Commits since the last
  release:
    - a breaking commit (`type!:`/`BREAKING CHANGE`) -> MAJOR,
    - `feat:` -> MINOR, anything
    - (`fix:` ...) -> PATCH.

This script computes the next version itself because no off-the-shelf tool (git-cliff included)
can parse a 4-segment version. git-cliff is only used to render `CHANGELOG.md`.

Usage:

    mise run release                 # auto bump from commits, show plan (dry-run by default)
    mise run release -- --apply      # actually commit CHANGELOG.md + create the tag
    mise run release -- --new-edition --apply
    mise run release -- --apply --push
"""

import argparse
import re
import subprocess
import sys

TAG_GLOB = "v[0-9]*.[0-9]*.[0-9]*.[0-9]*"
TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)\.(\d+)$")
BREAKING_SUBJECT = re.compile(r"^[a-zA-Z]+(\([^)]*\))?!:")
FEAT_SUBJECT = re.compile(r"^feat(\([^)]*\))?!?:")
RS, US = "\x1e", "\x1f"


def run(cmd: list[str], *, check: bool = True) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        sys.exit(f"command failed ({result.returncode}): {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()


def latest_tag() -> str | None:
    """Get the latest tag, if available."""
    out = run(["git", "tag", "--list", TAG_GLOB, "--sort=-v:refname"])
    for line in out.splitlines():
        if TAG_RE.match(line.strip()):
            return line.strip()
    return None


def parse_tag(tag: str) -> tuple[int, int, int, int]:
    match = TAG_RE.match(tag)
    if match is None:
        sys.exit(f"tag {tag!r} is not EDITION.MAJOR.MINOR.PATCH")
    return tuple(int(part) for part in match.groups())


def commits_since(tag: str | None) -> list[tuple[str, str]]:
    """Get all commits (summary, body) since the tag (or else HEAD)."""
    rev_range = f"{tag}..HEAD" if tag else "HEAD"
    out = run(["git", "log", rev_range, f"--format=%s{US}%b{RS}"])
    commits: list[tuple[str, str]] = []
    for record in out.split(RS):
        if not record.strip():
            continue
        subject, _, body = record.strip().partition(US)
        commits.append((subject.strip(), body))
    return commits


def decide_bump(commits: list[tuple[str, str]]) -> str | None:
    """Return 'major' | 'minor' | 'patch' from Conventional Commits, or None if no commits."""
    if not commits:
        return None
    breaking = any(
        BREAKING_SUBJECT.match(subject) or "BREAKING CHANGE" in body or "BREAKING-CHANGE" in body
        for subject, body in commits
    )
    if breaking:
        return "major"
    if any(FEAT_SUBJECT.match(subject) for subject, _ in commits):
        return "minor"
    return "patch"


def next_tag(current: tuple[int, int, int, int], bump: str | None, *, new_edition: bool) -> str:
    """Return the next tag string, bumping the current tag according to bump and new_edition."""
    edition, major, minor, patch = current
    if new_edition:
        return f"v{edition + 1}.0.0.0"
    if bump == "major":
        major, minor, patch = major + 1, 0, 0
    elif bump == "minor":
        minor, patch = minor + 1, 0
    elif bump == "patch":
        patch += 1
    return f"v{edition}.{major}.{minor}.{patch}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="commit CHANGELOG.md and tag (else dry-run)"
    )
    parser.add_argument(
        "--new-edition", action="store_true", help="bump EDITION; reset inner to 0.0.0"
    )
    parser.add_argument("--push", action="store_true", help="push the release commit and tag")
    args = parser.parse_args()

    current_tag = latest_tag()
    current = parse_tag(current_tag) if current_tag else (1, 0, 0, 0)
    commits = commits_since(current_tag)
    bump = decide_bump(commits)

    if not args.new_edition and bump is None:
        return

    target = next_tag(current, bump, new_edition=args.new_edition)
    reason = "EDITION (results not comparable)" if args.new_edition else f"{bump} (from commits)"

    if not args.apply:
        # Dry-run: show the plan and the changelog git-cliff would render for this tag.
        preview = run(["git-cliff", "--tag", target, "--unreleased"])
        print(f"{current_tag or '(no tags yet)'} -> {target}  [{reason}]\n\n{preview}")  # noqa: T201
        return

    # git-cliff renders the changelog; the unreleased commits are labelled with the new version.
    run(["git-cliff", "--tag", target, "--output", "CHANGELOG.md"])
    run(["git", "add", "CHANGELOG.md"])
    run(["git", "commit", "-m", f"chore(release): {target}"])
    run(["git", "tag", "-a", target, "-m", f"Release {target}"])
    if args.push:
        run(["git", "push"])
        run(["git", "push", "origin", target])


if __name__ == "__main__":
    main()
