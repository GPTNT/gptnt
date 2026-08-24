# Working in `tests/`

Read the [testing guide](../agent_docs/testing.md) before changing a test, fixture, factory, case
set, harness, or file under `tests/`. Its eighteen rules govern this directory and do not apply
under `src/`.

The ones that most often go wrong here:

|             |                                                                                                                              |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `gptnt:601` | Factory, cases class, harness, or fixture: pick by what the test is about. Do not wrap a one-line construction in a fixture. |
| `gptnt:602` | Assert something that could fail. "Does not raise" is not an observation.                                                    |
| `gptnt:604` | Do not test a value that only passes unchanged through typed call sites.                                                     |
| `gptnt:611` | Test contracts `gptnt` owns, not a dependency's.                                                                             |
| `gptnt:613` | Reduce parameter matrices. One representative input for pass-through behaviour.                                              |

## Layout

`_cases/`, `_factories/`, `_harness/`, and `_data/` hold the shared fixtures and fakes.
`_cli_runner.py` provides `invoke_cli`: use it for CLI behaviour, and call functions directly for
domain behaviour (`gptnt:603`).

## What to run

Targeted paths while developing. The full suite is slow.

```bash
uv run pytest tests/cli tests/experiments
```

Run integration tests separately when the combined run is unreliable (`gptnt:618`).

## Conventions in this directory

- **No `class Test…` groupings.** There are none left. Do not reintroduce them.
- **Name a test as the assertion it makes**, not as a topic:
  `test_absolute_missions_path_is_rejected` rather than `test_missions_path`.
- **One behaviour per test.** A name containing `_and_` usually means two assertions that want to be
  two tests (`gptnt:612`).
- **A docstring only when it explains what the name and assertions do not** (`gptnt:213`): an
  invariant, a calculation, or a fixture arrangement. No `"""Test …"""` prefixes.
- Markers: `integration`, `slow`, `requires_game` (`gptnt:608`).
