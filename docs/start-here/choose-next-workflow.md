---
title: Choose the next workflow
---

# Choose the next workflow

Choose a task after the included quickstart works. The checked installation and successful first
run are prerequisites for the execution and submission paths.

| Your current goal | Continue with |
| ----------------- | ------------- |
| Connect a model to GPTNT | [Add a model](../running/add-new-player.md){data-preview} |
| Configure suites, players, rooms, or displays | [Create a run manifest](../running/create-run-manifest.md){data-preview} |
| Prepare or inspect manuals | [Prepare manuals](../manuals.md){data-preview} |
| Run interactive experiments | [Run interactive experiments](../running/run-your-model.md) |
| Inspect Parquet and DuckDB results | [Inspect and analyse results](../running/inspect-results.md) |
| Build and validate a submission | [Submit your results](../submit-your-results.md){data-preview} |
| Understand models, players, roles, and services | [Understand GPTNT](../understand/index.md){data-preview} |
| Find exact commands, settings, or runtime contracts | [Reference](../reference/index.md){data-preview} |

The static-evaluation CLI uses `--player`, not the earlier `--model` spelling. Continue with
[Run static evaluations](../running/run-static-evaluations.md) for no-game tasks.

## Repeat checks after setup changes

Run the applicable [`doctor` mode](../reference/cli/doctor.md) after changing a player, provider,
run manifest, game installation, Redis endpoint, or display. Regenerate experiment specifications
after changing a manifest or configuration that affects the selected experiments.

<!-- vale ai-tells.DoubleHyphen = NO -->
[Understand GPTNT](../understand/index.md)
[Open the reference](../reference/index.md)
<!-- vale ai-tells.DoubleHyphen = YES -->
