# Contributing to GPTNT

> [!warning]
> This is a current work in progress.

## Versioning & releases

GPTNT is a **benchmark**, so a version exists to answer one question:

> _Are eval numbers from version X still comparable to version Y?_

### The scheme: `EDITION.MAJOR.MINOR.PATCH`

Example: `1.4.2.0`. This is valid [PEP 440](https://peps.python.org/pep-0440/) (so it stays `pip`-installable) even though it is **not** SemVer (which is 3 numbers).

| Segment     | Meaning                                                                                                                                                                  | Bumped by                        |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------- |
| **EDITION** | Result-comparability generation. A bump means **prior editions are NOT comparable**. Doubles as the marketing edition ("GPTNT 2"). Resets the inner numbers to `.0.0.0`. | **A human**, via `--new-edition` |
| **MAJOR**   | Breaking change to tooling / CLI / output API. Scores are **unaffected**.                                                                                                | `type!:` / `BREAKING CHANGE:`    |
| **MINOR**   | Additive — new tasks/features; existing scores untouched.                                                                                                                | `feat:`                          |
| **PATCH**   | Fix with no break and no score impact.                                                                                                                                   | `fix:` and everything else       |

### The one rule that matters

**Classify a change by its effect on scores, not by what kind of code change it is.**

- A "bug fix" that _changes produced numbers_ is an **EDITION** bump. Even though it's "just a fix", the results are now incomparable.
- A fix that doesn't touch scores is a **PATCH**.

**Same EDITION == comparable.** Eval results should cite the EDITION for comparability and the full version (+ git SHA) for exact reproduction. Both are stamped automatically into recorded runs.

### How versions are produced

The source of truth is **git tags** of the form `vEDITION.MAJOR.MINOR.PATCH`. [`uv-dynamic-versioning`](https://github.com/ninoseki/uv-dynamic-versioning) derives every package's version from the latest tag at build/sync time. Between releases you get `E.M.m.p.devN+g<sha>` automatically. **You should never need to hand-edit a version number anywhere.**

### Cutting a release

Releases are driven by [`scripts/release.py`](scripts/release.py) (wrapped as a mise task). It computes the next `MAJOR.MINOR.PATCH` from the Conventional Commits since the last release, renders `CHANGELOG.md` with [git-cliff](https://git-cliff.org), commits it, and creates the tag. (It computes the bump itself because git-cliff is SemVer-only and cannot parse a 4-segment version.)

```bash
mise run release                      # dry-run: show the computed bump + changelog preview
mise run release -- --apply           # commit CHANGELOG.md and create the tag
mise run release -- --apply --push    # ...and push the commit + tag
mise run release -- --new-edition --apply   # declare a new, incomparable edition (E+1.0.0.0)
```

Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org) (`feat:`, `fix:`, `feat!:` / `BREAKING CHANGE:`), which this repo already uses.
