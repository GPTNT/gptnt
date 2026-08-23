---
title: Submission validation
tags:
  - Submission
  - Results
---

# Submission validation

Use the failed check name to select the correction. Rebuild derived content with
`gptnt submission new`. Edit only submitter fields by hand.

## No bundles are found

`submission validate` searches recursively for `submission.yaml`. Confirm that `--path` identifies
one bundle or the root written by `submission new`. An empty root is an error.

## The manifest or payload does not parse

- `schema_version` must be `2`. A schema-v1 bundle needs matching v1 tooling.
- `measured` must describe exactly one suite or one static task.
- Interactive bundles need `experiments.parquet` and `suite.lock`.
- Static bundles need valid JSON in `metrics.json`.
- A bundle must not contain the other variant's payload.

Do not add or remove derived fields to make parsing pass. Rebuild from DuckDB or the static output
directory.

## Submitter fields are blank

Fill `submitter.name` and `submitter.contact` in `submission.yaml`, or supply the nested options to
`submission new`. `submitter.affiliation` can remain null.

## Naming or fingerprint checks fail

The directory name, `submission_id`, and serialized player fingerprint are derived from manifest
data. A mismatch indicates manual editing or output from different code. Rebuild the bundle.

## Suite or coverage checks fail

An interactive bundle must contain one reduced suite-lock entry whose digest and mission bodies
match the manifest and payload. It must contain exactly one valid run for each expected Defuser,
Expert, and mission pairing.

- `missing`: rerun the listed mission and rebuild DuckDB.
- `duplicates`: curate retries so one run remains for each pairing and mission.
- `unknown`: remove rows that do not belong to the frozen suite snapshot.
- `outcomes`: rerun incomplete, crashed, or non-terminal experiments.

Preserve the source player-record Parquet while making these corrections.

## Provenance fails

`gptnt_version` must match the recorded release tag, and `release_commit` must be a complete
lowercase commit SHA. Every interactive payload row must match the manifest provenance.

!!! danger "Do not rewrite protected state"
    `protected_content_modified: true` means the benchmark ran with protected content different
    from the tagged release. Validation rejects it. Restore the tagged release and rerun the
    affected results instead of editing the bundle.

An unpinned static dataset is a warning rather than a failed check. Rerun with
`--dataset-revision <ref>` while online so `run_meta.json` records a resolved commit.

## Dry-run or remote submission fails

Install the submission extra. Set `GITHUB_TOKEN`, or ensure `gh auth token` succeeds. Confirm that
`--repo` uses `owner/name` form and that the account can read the target repository. A dry run
still authenticates, looks up the repository, and clones it. Only GitHub mutations are suppressed.

[Submit results](../run-and-submit/submit-results.md)
[Submission bundle format](../reference/files/submission-bundles.md)
