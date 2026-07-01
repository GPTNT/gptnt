# Versioning Policy

Since this is a benchmark _and_ a library, it is incredibly important that models are compared on an equal footing, but also that we are not constantly breaking or gating results on new versions. From this, we have a 2-tier versioning policy: one for the codebase, and one for the benchmark.

## Codebase versioning

The codebase follows [Semantic Versioning](https://semver.org/), and is automated through [Conventional Commits](https://conventionalcommits.org). All pull requests must ensure that the _title_ follows conventional commits.[^1]

[^1]: We encourage squashing PR's by default. Therefore, you can make the individual commits whatever you want, but the PR title must follow conventional commits. The CI will check this and complain at you until you fix it.

## Benchmark versioning
