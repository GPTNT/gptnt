---
title: Choose the next workflow
---

# Choose the next workflow

Choose a task after the included quickstart works. The checked installation and successful first
run are prerequisites for the execution and submission paths.

| Your current goal | Continue with |
| ----------------- | ------------- |
| Connect a model to GPTNT | [Add a model](../run-and-submit/add-model.md){data-preview} |
| Configure suites, players, rooms, or displays | [Create a run manifest](../run-and-submit/create-run-manifest.md){data-preview} |
| Prepare or inspect manuals | [Prepare manuals](../run-and-submit/prepare-manuals.md){data-preview} |
| Run interactive experiments | [Run interactive experiments](../run-and-submit/run-interactive.md) |
| Inspect Parquet and DuckDB results | [Inspect and analyse results](../run-and-submit/inspect-results.md) |
| Build and validate a submission | [Submit your results](../run-and-submit/submit-results.md){data-preview} |
| Understand models, players, roles, and services | [Understand GPTNT](../understand/index.md){data-preview} |
| Find exact commands, settings, or runtime contracts | [Reference](../reference/index.md){data-preview} |

The static-evaluation CLI uses `--player`, not the earlier `--model` spelling. Continue with
[Run static evaluations](../run-and-submit/run-statics.md) for no-game tasks.

## Repeat checks after setup changes

Run the applicable [`doctor` mode](../reference/cli/doctor.md) after changing a player, provider,
run manifest, game installation, Redis endpoint, or display. Regenerate experiment specifications
after changing a manifest or configuration that affects the selected experiments.

[Understand GPTNT](../understand/index.md)
[Open the reference](../reference/index.md)
