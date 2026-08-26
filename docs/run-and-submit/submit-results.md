---
title: Submit your results
tags:
  - Submission
  - Results
  - CLI
---

# Submit your results

Build one schema-version-2 bundle per model and target, validate it locally, preview the repository
operation, and open pull requests against
[gptnt/submissions](https://github.com/gptnt/submissions).

## Prepare the required results

Complete these interactive suites:

- `multi-self-async`
- `multi-self-sync`
- `single-parametric-sync`

Also complete the explicit `expert-vqa-no-manual` static target. Every submitted player needs an
`identity` block in `configs/player/<player-name>.yaml`; see
[Configure the player](add-model.md#configure-the-player){data-preview}.

Use [Inspect and analyse results](inspect-results.md) to confirm terminal outcomes, build
DuckDB, and check the static metadata and metrics. Run from an unmodified tagged release;
submission bundle construction has no modified-benchmark override.

Install the remote-submission dependency group before the final stage:

```bash title="Run in your shell"
uv sync --all-groups --extra submission
```

Set `GITHUB_TOKEN`, or install and authenticate the GitHub CLI with `gh auth login`.

## Collate the interactive records

```bash title="Run in your shell"
gptnt build-db <directory-of-experiment-outputs> \
  --output output/experiments.duckdb
```

!!! warning "Keep the source Parquet"
    Preserve the player-record Parquet through bundle construction and successful validation.
    DuckDB and bundle payloads are derived data. Retained records allow either to be rebuilt.

## Build the bundles

```bash title="Run in your shell"
gptnt submission new \
  --suite multi-self-async \
  --suite multi-self-sync \
  --suite single-parametric-sync \
  --static expert-vqa-no-manual \
  --submitter.name "<name>" \
  --submitter.contact "@<handle>" \
  --submitter.affiliation "<affiliation>"
```

`multi-self-async`, `multi-self-sync`, and `single-parametric-sync` are the interactive defaults,
but stating them in a release command makes the intended selection visible. Static targets have no
default, so pass `--static expert-vqa-no-manual` explicitly. `--submitter.contact` accepts a GitHub
handle or an email, and affiliation is optional. Use `--experiments-db`, `--statics-output-dir`, or
`--output-dir` when your files are outside their default locations. Use `--model` to select player
configuration names present in the data.

The builder creates one flat directory per capability fingerprint and target. An interactive
bundle contains `submission.yaml`, `experiments.parquet`, and `suite.lock`. The last file is a
reduced snapshot of `configs/suites/suites.lock`. A static bundle contains `submission.yaml` and a
verbatim `metrics.json`.

```text
output/submissions/
├── <interactive-bundle>/
│   ├── submission.yaml
│   ├── suite.lock
│   └── experiments.parquet
└── <static-bundle>/
    ├── submission.yaml
    └── metrics.json
```

`submission.yaml` uses submission schema version 2. Its `provenance` block records `gptnt_version`,
the benchmark reference in `release_tag`, `release_commit`, and `protected_content_modified`. It
also records player capabilities and fingerprints and the measured suite or static identity. See
[Roles, protocols, and capabilities](../understand/roles-protocols-and-capabilities.md#identity-and-fingerprints-serve-different-purposes)
for player fingerprints and
[Suites, revisions, and comparability](../understand/suites-revisions-and-comparability.md) for
benchmark references and suite digests.

An interactive bundle also includes `suite.lock`, reduced to the recorded suite revision and the
missions it references. Validation therefore checks the included suite snapshot instead of reading
the current `configs/suites` and `configs/missions` files. `experiments.parquet` contains an
`ExperimentSummary`, outcome, and per-player usage for each submitted experiment; it does not
contain the full trajectories. A static bundle contains its aggregated scorer output in
`metrics.json`.

The player display name and attribution come from the config's `identity` block. The measured
capabilities and player fingerprint come from the records. Do not hand-edit derived identities in
`submission.yaml`: validation recomputes them and rejects a mismatch.
You may fill the `submitter` block after building. A rebuild preserves an existing valid block.

## Validate the bundles

```bash title="Run in your shell"
gptnt submission validate output/submissions
```

The command accepts one bundle directory or a root to sweep. It checks manifest and payload shape,
directory and submission IDs, submitter fields, fingerprints, provenance, protected state, and the
payload kind. Interactive validation also checks the reduced suite snapshot, suite digest, exact
mission coverage, terminal outcomes, and players. Static validation warns when the dataset has no
resolved commit.

!!! danger "Modified protected content is not submittable"
    Validation rejects `protected_content_modified: true`. Restore the release checkout and rerun
    the benchmark. Do not edit the stored flag or derived provenance.

!!! success "The bundle is ready"
    Every bundle report has no failed checks. Warnings remain visible and should be resolved when
    they affect reproducibility, including an unpinned static dataset.

The submissions repository first verifies the GPTNT release identified by the recorded release tag
and commit. It then requires the bundle suite snapshot to exactly match that release's suite
registry. A later release can have a different bundle contract, so the recorded release is the
validation boundary.

## Preview and submit

```bash title="Run in your shell"
gptnt submission submit --dry-run
```

The dry run authenticates and reads the repository before creating a local clone, branches, and
commits. It does not fork, push, or open a pull request. Review the bundle, branch, staged paths,
and pull-request title printed for every bundle.

Submit after the preview is correct:

```bash title="Run in your shell"
gptnt submission submit
```

The command opens or refreshes one pull request per top-level bundle. It pushes directly when your
account has access; otherwise it creates or uses a fork. A failure for one bundle is reported while
the remaining bundles continue.
