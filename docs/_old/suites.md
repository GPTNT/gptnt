# Suites

The committed suites and their revisions. Each is `configs/suites/<name>.yaml`.
`tests/experiments/test_frozen_suites.py` pins each suite's content and missions, so a
score-determining change requires a `revision` bump recorded here. See `docs/comparability.md` for
what a suite is.

`multi-self-sync` and `multi-self-async` are the headline suites: one model plays both roles across
the multi-module set. The rest are single-module suites and baselines.

| Suite                     | Rev | Mission set       | Matchup   | Communication | Players                       |
| ------------------------- | --- | ----------------- | --------- | ------------- | ----------------------------- |
| `multi-self-sync`         | 1   | multiple_module_n | with_self | sync          | defuser + expert (same model) |
| `multi-self-async`        | 1   | multiple_module_n | with_self | async         | defuser + expert (same model) |
| `single-pairwise-sync`    | 1   | single_module     | pairwise  | sync          | every defuser × every expert  |
| `single-self-async`       | 1   | single_module     | with_self | async         | defuser + expert (same model) |
| `single-parametric-sync`  | 1   | single_module     | no_expert | sync          | solo defuser, no manual       |
| `single-solo-player-sync` | 1   | single_module     | no_expert | sync          | solo defuser, with manual     |

## Revision history

All suites are at revision 1.
