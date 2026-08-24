# Working in `gptnt`

Orientation for any agent or human working in this repo. The coding rules live in
[`agent_docs/`](agent_docs/).

## Always-read guardrails

These guardrails and the linked rule guidance apply to AI agents. They do not impose a workflow on
human contributors.

- Use the guide selected by the action or path in the
  [`rule guide index`](agent_docs/index.md). A rule is conditional on its trigger, not optional.
- Keep the change within its stated objective and preserve unrelated worktree changes. See
  [`workflow.md`](agent_docs/workflow.md) before choosing task scope.
- Before changing a public interface, configuration schema, package boundary, shared type, or
  behaviour across several files, read [`workflow.md`](agent_docs/workflow.md).
- Use [`workflow.md`](agent_docs/workflow.md) to select proportionate tests and final verification.

## Action routing

| When you need to...                                                               | Read                                                                |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Change a public interface, task scope, user decision, or test selection           | [`workflow.md`](agent_docs/workflow.md)                             |
| Add, move, replace, name, or expose code                                          | [`architecture.md`](agent_docs/architecture.md)                     |
| Change data models, types, errors, or tests                                       | The matching guide in the [`rule guide index`](agent_docs/index.md) |
| Add a command, configuration, model reference, runtime service, log, or timestamp | [`cli-config-runtime.md`](agent_docs/cli-config-runtime.md)         |
| Write prose or change documentation                                               | [`writing-and-docs.md`](agent_docs/writing-and-docs.md)             |

For detailed routing, use the [`rule guide index`](agent_docs/index.md). For test-local conventions,
also read the [`tests/AGENTS.md`](tests/AGENTS.md) overlay.

### Subagents

Some subagent configurations do not load repository instructions. Tell a subagent expected to
follow these rules to read this file and the relevant guide before it starts work.

### Agent completion

This section applies to AI agents. It does not impose a workflow on human contributors.

Before presenting a change as ready, an AI agent must:

- Run the narrowest relevant tests when behaviour, configuration, or tests changed. Run the full
  suite only when the change warrants it (`gptnt:104`).
- Run `mise run format`.
- Run `mise exec -- vale sync` before the first Vale check in a worktree.
- Run `mise exec -- vale <changed Markdown and Python prose files>` when prose changed.
- Report the commands run, their outcomes, and any check that was not applicable or could not run.

## 1. Project overview

GPTNT is an AI benchmark built on **KTANE** ("Keep Talking and Nobody Explodes"). KTANE is a co-op
bomb-defusal game. A _Defuser_ can see the bomb but not the manual. An _Expert_ can read the manual
but not the bomb. They must talk to each other to defuse it. Here the players are AI models paired
through pydantic-ai. You run **experiments** that pair models against bombs and record how well they
do. Users generate experiments, and GPTNT runs and records them. There is also a **statics** path
for no-game evaluations against HuggingFace datasets.

## 2. Quick reference

This is a `uv` package, under `src/gptnt/`. Python >=3.13 and `uv` are provided through `mise`.
Tasks run through `mise`:

```bash
mise run sync      # install all dependency groups and extras
mise run format    # format + lint everything in one pass
mise run tests     # the full pytest suite
mise run release   # bump the version, create a tag, and update CHANGELOG.md
```

Run tests on specific paths while iterating. Do not run the full suite during development, it is slow:

```bash
uv run pytest tests/cli tests/experiments    # targeted
```

The CLI entry point is `gptnt` (`gptnt.cli.__main__:main`). The usual first run is `gptnt doctor` to
check the machine is ready, then `gptnt run <run.yaml>` to spawn the game and players, submit
pre-generated specs, and monitor.

## 3. Project structure & layering

```text
src/gptnt/
  common/            foundational wrappers, config, and primitives (not a utils bucket)
  ktane/             KTANE domain: game client, state, actions, mission spec
  players/           LM player loop: action prediction, parsing, observations, shared specs
                     (specification.py: player protocols, roles, capabilities)
  processors/        image preprocessing for vision models (set-of-marks, resize)
  prompts/           instructions, manual text, output schema
  observability/     OTLP span instrumentation and timing
  provenance/        release and benchmark-integrity metadata
  experiments/       spec generation, recording, the DuckDB layer, wandb
  interactive/       run orchestration and runtime services: experiment manager (EM), redis, spawn
  app/               Streamlit analysis dashboard
  statics/           no-game evaluations against HuggingFace datasets
  cli/               the cyclopts command surface (assembles everything)

tests/
  _cases/  _factories/  _harness/  _data/   shared fixtures and fakes
  _cli_runner.py                            cyclopts test driver (invoke_cli)
  cli/ core/ experiments/ interactive/ records/ statics/ integration/
```

import-linter contracts in `pyproject.toml` enforce one-way dependencies between the subpackages:

```text
common, observability, provenance
  ← ktane
  ← players, processors, prompts
  ← experiments
  ← statics, app, interactive
  ← cli
```

`common`, `observability`, and `provenance` form the bottom layer. `cli` is the top-level
assembler, and nothing should import it. The rules for imports, privacy, and code placement are in
the [`architecture guide`](agent_docs/architecture.md).
