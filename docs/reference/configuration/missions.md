---
title: Mission configuration
tags:
  - Configuration
---

# Mission configuration

Mission recipes generate materialised KTANE mission JSON. Suites and suite locks reference those
files, while the run path never invokes the recipe.

## Recipe and materialisation

`configs/missions/recipes/<name>.yaml` constructs `MissionGenerator` and its
`MissionGeneratorConfig`. Materialise it with:

```bash title="Run in your shell"
gptnt generate-missions <name>
```

The command writes `configs/missions/<name>/<sorted-modules>-<seed>.json`. Module-count and optional-
widget bounds are inclusive. With `sample_from_modules: true`, the generator emits one sampled
mission per seed. With it disabled, the generator emits one mission per available module per seed.

## Materialised JSON

The stored KTANE aliases are `ruleSeed`, `timeLimit`, `numStrikes`, `optWidgets`, `needyTime`,
`isFront`, `timeScale`, and `timeStepSize`. `mission_key` is derived from both seeds and the sorted
component names. `timeStepSize` is the number of milliseconds advanced by a timestep command.

## Generated models

::: gptnt.experiments.generation.missions.MissionGeneratorConfig
    options:
      show_root_heading: true
      members:
        - available_modules
        - expected_num_missions

::: gptnt.experiments.generation.missions.MissionGenerator
    options:
      show_root_heading: true
      members:
        - generate

::: gptnt.ktane.mission_spec.KtaneMissionSpec
    options:
      show_root_heading: true
      members:
        - mission_key
        - requires_multiple_images_per_observation
        - to_query_params
