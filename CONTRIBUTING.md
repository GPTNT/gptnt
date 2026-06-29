# Contributing to GPTNT

> [!warning]
> This is a current work in progress.

## Versioning & releases

GPTNT uses standard [SemVer](https://semver.org). We are **pre-1.0**: every release is `0.x` and the
public surface (CLI, output schema, scores) is not yet stable. `v1.0.0` is reserved for the first
stable benchmark.

### The scheme

| Segment   | Pre-1.0 (now)                                           | Post-1.0                                                |
| --------- | ------------------------------------------------------- | ------------------------------------------------------- |
| **MAJOR** | Stays `0`.                                              | A breaking change. **Eval scores may be incomparable.** |
| **MINOR** | A breaking change _or_ an overhaul (the `0.x` "major"). | Additive — new tasks/features; existing scores intact.  |
| **PATCH** | Everything additive — new features and fixes.           | A fix with no break and no score impact.                |

While `MAJOR` is `0`, a breaking commit bumps **MINOR** (not to `1.0.0`), and a `feat`/`fix` bumps
**PATCH**. This is commitizen's `major_version_zero` behaviour and is configured in `pyproject.toml`.

Comparability is judged on **MAJOR** once we are past `1.0.0` (same major ⇒ comparable). The full
version and git SHA are stamped into every recorded run for exact reproduction (see
[`provenance.py`](src/gptnt/experiments/provenance.py)).

### How versions are produced

The source of truth is **git tags** of the form `vMAJOR.MINOR.PATCH`.
[`uv-dynamic-versioning`](https://github.com/ninoseki/uv-dynamic-versioning) derives the package
version from the latest tag at build/sync time; between releases you get `X.Y.Z.devN+g<sha>`
automatically. **Never hand-edit a version number anywhere.**

### Cutting a release

Releases are driven by [commitizen](https://commitizen-tools.github.io/commitizen/) `cz bump`, which
derives the next SemVer from the Conventional Commits since the last tag, updates `CHANGELOG.md`, and
creates the tag.

```bash
mise run release                 # == `cz bump`: bump, tag, update CHANGELOG.md
mise run release -- --dry-run    # preview the computed bump without changing anything
cz bump --increment MAJOR        # when ready to declare v1.0.0
git push --follow-tags           # publish the release commit + tag
```

Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org) (`feat:`,
`fix:`, `feat!:` / `BREAKING CHANGE:`), which this repo already uses and the commitizen pre-commit
hook enforces.
