# Leaderboard publication design

## Purpose

Publish verified submission results to the GPTNT website without copying
metrics by hand. The public leaderboard must distinguish the new randomized
manual benchmark from the earlier leaderboard, which used the original KTANE
solutions.

## Scope

The publication path spans three repositories.

- `GPTNT/gptnt` aggregates submitted bundles into the website artifact.
- `GPTNT/submissions` validates bundles and runs the publication workflow after
  a merge to `main`.
- `GPTNT/gptnt.github.io` renders the current artifact and retains the original
  leaderboard as a historical page.

The selected approach is an automated, reviewable cross-repository pull
request. It replaces manual artifact copying while preserving a website review
before publication. Direct pushes to the website default branch are excluded
because benchmark output should remain reviewable.

## Submission validation

`scripts/validate_published_release.py` in `GPTNT/submissions` currently makes
the GitHub tag and release API requests without credentials. This can receive a
403 response even for a public release. The validation workflow already has a
read-only repository token, but does not pass it to the script.

The script will accept `GITHUB_TOKEN` from its environment and use it only for
the tag and release metadata lookups. The workflow will map
`${{ secrets.GITHUB_TOKEN }}` into that environment variable. The script will
continue to remove `GITHUB_TOKEN` before it invokes a validator from the
downloaded release archive. Untrusted submission contents must never receive
the workflow credential.

## Generated artifact

`gptnt leaderboard build <submissions-dir> --output <path>` will read every
published submission bundle beneath `submissions-dir/submissions`. It will
select `multi-self-async` and `multi-self-sync` entries whose suite revision is
at least 2, validate the expected flat bundle layout, parse each manifest and
interactive Parquet payload, and emit `leaderboard.generated.json` with the
documented schema. The output retains each selected entry's exact revision and
digest.

The command will calculate all displayed metrics from the experiment records:
mission solved percentage, module solved percentage, any-module solved
percentage, mean strikes, timeout percentage, detonation percentage,
module-level counts, and mean per-role token usage. It will retain player
identity, capabilities, suite revision and digest, and run provenance so the
website can show detailed records without a second data source.

The output will be deterministic: equivalent bundle contents produce the same
JSON ordering and values. A schema or golden-artifact test will cover the
contract from representative submission bundles.

## Publication workflow

On a push to `GPTNT/submissions` `main` that changes `submissions/**`, or a
manual `workflow_dispatch` run, a workflow will:

1. Check out the merged submissions repository.
2. Install the pinned GPTNT aggregator version and build the artifact.
3. Check out `GPTNT/gptnt.github.io`.
4. Replace only `src/data/leaderboard.generated.json` when its contents differ.
5. Open or update one dedicated pull request against the website repository.

The normal Actions `GITHUB_TOKEN` is scoped to `GPTNT/submissions`; it cannot
create a pull request in the website repository. The workflow therefore needs
a separately configured, least-privilege credential, such as a GitHub App
installation token or a fine-grained token, with website repository contents
write and pull-request write permissions. The credential is stored as a secret
in `GPTNT/submissions`, not committed to either repository.

If the artifact is unchanged, the workflow succeeds without opening a pull
request. If publication fails, it reports the failure but does not alter merged
submission data. The manual trigger creates the initial artifact from bundles
merged before the workflow existed. The manual trigger and merge-triggered run
use the same workflow, which checks out `GPTNT/submissions` afresh; neither
depends on a maintainer's local submission directory.

The publication workflow sends a direct email only when it opens or updates
the website pull request, or when validation or publication fails. The email
links to the relevant pull request or workflow run and names the required
maintainer action. It uses a provider API key stored as a
`GPTNT/submissions` repository secret and a verified sender address or domain.
Routine runs with no artifact change send no email.

## Website transition

The website will preserve the current generated artifact and its existing board
on a historical route. The historical page will state that its results use the
original KTANE rule tables and solutions and will be linked unobtrusively from
the active leaderboard.

The homepage will retain the current leaderboard format while consuming the
new generated artifact. Its editorial overlay will identify models absent from
the historical board as new. A News entry will introduce the new model results
and state that they use randomized manual solutions. The first website PR that
contains the new artifact will include these editorial changes so the page does
not label old results as the new benchmark. Later generated-artifact pull
requests update data only; creating later News entries remains an editorial
decision.

## Verification

- Unit-test the aggregator's manifest, payload, metric, ordering, and error
  handling paths.
- Run the existing published-release validator tests with a token-bearing
  environment and confirm the token is absent from the downloaded-release
  subprocess environment.
- Exercise the submissions workflow on a test branch or with a dry-run mode
  before granting the cross-repository credential production access.
- Build the website and inspect the homepage and historical route before
  merging the first generated-artifact PR.
