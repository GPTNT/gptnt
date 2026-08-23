---
title: Submit your results
---

# Submit your results

A submission is a self-contained bundle of recorded results and the identities needed to validate
them. You build and check the bundle locally, then open a pull request against the separate
[gptnt/submissions](https://github.com/gptnt/submissions) registry.

Submitting takes four steps:

1. [Collate](#collate-the-results) experiment outputs into DuckDB.
2. [Build](#build-the-bundles) one bundle per model and target.
3. [Validate](#validate-the-bundles) the bundle locally and in the registry.
4. [Submit](#open-the-pull-request) it by pull request.

## Before you start

Run these interactive suites:

- `multi-self-async`
- `multi-self-sync`
- `single-parametric-sync`

Also run the `expert-vqa-no-manual` static evaluation. Each submitted player must have an
`identity` block in `configs/player/<player-name>.yaml`; see
[Configure the player](running/add-new-player.md#configure-the-player){data-preview}.

Install the submission dependencies before opening a pull request:

```bash
uv sync --all-groups --extra submission
```

Set `GITHUB_TOKEN`, or authenticate the GitHub CLI with `gh auth login`. Local repository work uses
`pygit2`, so the system Git executable is not required.

## Collate the results

Each interactive experiment writes player records under the recorder output directory. Collate
them into one DuckDB file:

```bash
gptnt build-db <directory-of-experiment-outputs> -o output/experiments.duckdb
```

The DuckDB file is the input to the interactive submission builder. Keep the original Parquet files
until you have built and validated the bundles, because they are the source records if collation or
bundle construction must be repeated.

## Build the bundles

```bash
gptnt submission new \
  --suite multi-self-async \
  --suite multi-self-sync \
  --suite single-parametric-sync \
  --static expert-vqa-no-manual \
  --submitter.name "<name>" \
  --submitter.contact "@<handle>" \
  --submitter.affiliation "<affiliation>"
```

`--submitter.contact` accepts a GitHub handle or an email. Affiliation is optional. Use
`--experiments-db`, `--statics-output-dir`, or `--output-dir` when your files are outside their
default locations. Pass `--model` to select players.

The builder writes one directory per model and target under `output/submissions/`:

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
also records player capabilities and fingerprints and the measured suite or static identity. The
terms benchmark reference, player fingerprint, and suite digest are defined in
[Run your model](running/run-your-model.md#understand-benchmark-identity-and-editable-inputs),
[Roles, protocols, and capabilities](understand/roles-protocols-and-capabilities.md#identity-and-fingerprints-serve-different-purposes), and
[Adding or changing a suite](running/run-your-model.md#adding-or-changing-a-suite).

An interactive bundle also includes `suite.lock`, reduced to the recorded suite revision and the
missions it references. Validation therefore checks the included suite snapshot instead of reading
the current `configs/suites` and `configs/missions` files. `experiments.parquet` contains an
`ExperimentSummary`, outcome, and per-player usage for each submitted experiment; it does not
contain the full trajectories. A static bundle contains its aggregated scorer output in
`metrics.json`.

The player display name and attribution come from the config's `identity` block. The measured
capabilities and player fingerprint come from the records. Do not hand-edit derived identities in
`submission.yaml`: validation recomputes them and rejects a mismatch.

## Validate the bundles

### Local validation

```bash
gptnt submission validate
```

Local validation uses your current checkout and does not use the network. It checks the manifest,
recorded provenance, player fingerprints, included suite snapshot and suite digest, mission
coverage, player coverage, and outcomes. Pass a bundle directory or another root path to validate
something outside `output/submissions/`.

!!! warning "Modified protected content cannot be submitted"
    Contributor runs may use `--allow-modified-benchmark`, but their records set
    `protected_content_modified: true`. Submission validation rejects those records because they do
    not match the protected content at the recorded benchmark reference. Restore the release and
    rerun the benchmark before building a submission.

### Published validation

The registry check treats the recorded benchmark reference as the validator boundary. It downloads
`gptnt.tar.gz` and `gptnt.tar.gz.sha256` from that tag's
`/releases/download/vX.Y.Z/` path, verifies the checksum and `release_commit`, and runs the
validator from that release. It never uses `/releases/latest/download/`, because the latest release
may implement a different submission contract from the one that wrote the records.

For the boundary around prior formats, see [Prior artifacts](get-started.md#prior-artifacts).

## Open the pull request

Run the submission flow locally first:

```bash
gptnt submission submit --dry-run
```

The dry run authenticates and clones the registry. It creates local branches with commits, then
prints what each pull request would contain. It does not fork, push, or open a pull request.

When the output is correct, submit the bundles:

```bash
gptnt submission submit
```

The command opens one pull request per bundle. It pushes directly when you have registry access;
otherwise it creates a fork. Re-running updates the branch and existing pull request.
