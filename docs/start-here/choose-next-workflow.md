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
| Run interactive experiments | [Run your model](../running/run-your-model.md#interactive-experiments) |
| Inspect Parquet and DuckDB results | [Read the results](../running/run-your-model.md#read-the-results) |
| Build and validate a submission | [Submit your results](../submit-your-results.md){data-preview} |
| Understand models, players, roles, and services | [Understand GPTNT](../understand/index.md){data-preview} |
| Find exact commands, settings, or runtime contracts | [Reference](../reference/index.md){data-preview} |

Static-evaluation and expanded result procedures will join this route when their connected Slice C
pages are integrated. The current static CLI uses `--player`, not `--model`.

## Repeat checks after setup changes

Run the applicable [`doctor` mode](../reference/cli/doctor.md) after changing a player, provider,
run manifest, game installation, Redis endpoint, or display. Regenerate experiment specifications
after changing a manifest or configuration that affects the selected experiments.

<!-- vale ai-tells.DoubleHyphen = NO -->
[Understand GPTNT](../understand/index.md)
[Open the reference](../reference/index.md)
<!-- vale ai-tells.DoubleHyphen = YES -->
