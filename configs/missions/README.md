# Mission library

Frozen `KtaneMissionSpec` JSON files, grouped into sets that a suite loads by path
(`missions_path` in `configs/suites/<id>.yaml`). These files are the source of truth: a run loads
them and never generates. Editing any file changes the loading suite's `missions_digest`, so
freeze the relevant suite revision when preparing a separate `suites.lock` update.

## Sets

- `single_module/`: generated from `recipes/single_module.yaml` with
  `gptnt generate-missions single_module`. The recipe records how the files were produced, so the
  set is reproducible.
- `multiple_module_n/`: a curated set, authored and edited by hand. It has no recipe.
