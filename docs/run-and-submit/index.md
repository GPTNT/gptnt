---
title: Run and submit
---

# Run and submit

Start here after the included-player quickstart works. These procedures take a model from local
configuration through experiment execution, result inspection, and submission.

!!! warning "Complete the quickstart first"
    The procedures assume that `gptnt doctor` can reach Redis and KTANE and that the
    [quickstart](../start-here/run-quickstart.md){data-preview} has produced a queryable result.

## Configure the inputs

| Goal | Procedure | Result |
| ---- | --------- | ------ |
| Assemble a model-backed player | [Add a model](add-model.md){data-preview} | A player profile with identity, capabilities, model settings, and image-token calibration |
| Connect the player to an endpoint | [Configure a provider](configure-provider.md){data-preview} | Credentials and any provider override supplied outside the player profile |
| Prepare the manual selected by a suite | [Prepare manuals](prepare-manuals.md){data-preview} | Validated, content-addressed manual artefacts |
| Select suites, players, and runtime capacity | [Create a run manifest](create-run-manifest.md){data-preview} | A schema-v2 manifest and generated experiment specifications |

## Execute and submit

1. [Run your model](run-interactive.md){data-preview} to execute the generated interactive
   specifications.
2. [Run static evaluations](run-statics.md){data-preview} for the required no-game
   tasks.
3. [Inspect and analyse results](inspect-results.md){data-preview} to check completion and build
   DuckDB.
4. [Submit your results](submit-results.md){data-preview} after the interactive and static
   outputs are complete.

Use [roles, protocols, and capabilities](../understand/roles-protocols-and-capabilities.md) when a
suite's participation rules affect a player choice. Use the [reference](../reference/index.md) for
exact commands, fields, formats, and supported Python interfaces.
