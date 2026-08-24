# `gptnt` rule guide index

Use this page to select the guide for the change in front of you. It is a routing page; each topic
guide contains the canonical rule text. A rule is conditional on its trigger, not optional.

## Route by action

| When you need to...                                                                         | Read                                                                   |
| ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Change a public boundary, choose task scope, ask the user to decide, or select verification | [`workflow.md`](workflow.md)                                           |
| Add, move, replace, name, or expose code                                                    | [`architecture.md`](architecture.md)                                   |
| Model data, define fields, or annotate types                                                | [`data-and-types.md`](data-and-types.md)                               |
| Choose an error convention, validation boundary, or resource cleanup                        | [`errors.md`](errors.md)                                               |
| Change tests, fixtures, factories, cases, or harnesses                                      | [`testing.md`](testing.md) and [`tests/AGENTS.md`](../tests/AGENTS.md) |
| Add a command, configuration, model reference, runtime service, log, or timestamp           | [`cli-config-runtime.md`](cli-config-runtime.md)                       |
| Write prose, documentation, comments, or docstrings                                         | [`writing-and-docs.md`](writing-and-docs.md)                           |
| Format, lint, or verify a change                                                            | [`lint.md`](lint.md)                                                   |
| Change recorded output or prepare a release                                                 | [`records-and-releases.md`](records-and-releases.md)                   |

## Route by changed path

| Changed path                                                                                             | Read                                                                                 |
| -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `AGENTS.md`, public API, configuration schema, or shared type                                            | [`workflow.md`](workflow.md) and the guide for the affected code                     |
| `src/gptnt/common/`, `ktane/`, `players/`, `processors/`, `prompts/`, `observability/`, or `provenance/` | [`architecture.md`](architecture.md) and the guide for the change's action           |
| `src/gptnt/experiments/`, `statics/`, `app/`, `interactive/`, or `cli/`                                  | [`architecture.md`](architecture.md) and the guide for the change's action           |
| `tests/`                                                                                                 | [`testing.md`](testing.md) and [`tests/AGENTS.md`](../tests/AGENTS.md)               |
| `agent_docs/`, `docs/`, or another Markdown file                                                         | [`writing-and-docs.md`](writing-and-docs.md) and the guide for the documented action |
| Recorded data or release records                                                                         | [`records-and-releases.md`](records-and-releases.md)                                 |

## Canonical rule map

| Rule IDs                                                                                                                                   | Canonical guide                                                                                         |
| ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| `gptnt:101` to `gptnt:104`                                                                                                                 | [`workflow.md`](workflow.md)                                                                            |
| `gptnt:2xx`                                                                                                                                | [`writing-and-docs.md`](writing-and-docs.md)                                                            |
| `gptnt:301` to `gptnt:309`, `gptnt:311` to `gptnt:314`, `gptnt:316` to `gptnt:322`, `gptnt:324` to `gptnt:325`, `gptnt:327` to `gptnt:328` | [`architecture.md`](architecture.md)                                                                    |
| `gptnt:310`, `gptnt:323`                                                                                                                   | [`cli-config-runtime.md`](cli-config-runtime.md). These are exceptions to the `3xx` architecture range. |
| `gptnt:4xx`                                                                                                                                | [`data-and-types.md`](data-and-types.md)                                                                |
| `gptnt:5xx`                                                                                                                                | [`errors.md`](errors.md)                                                                                |
| `gptnt:6xx`                                                                                                                                | [`testing.md`](testing.md) and [`tests/AGENTS.md`](../tests/AGENTS.md)                                  |
| `gptnt:7xx`                                                                                                                                | [`cli-config-runtime.md`](cli-config-runtime.md)                                                        |
| `gptnt:801` to `gptnt:802`                                                                                                                 | [`lint.md`](lint.md)                                                                                    |
| `gptnt:901`                                                                                                                                | [`records-and-releases.md`](records-and-releases.md)                                                    |
