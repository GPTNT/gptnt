# Run your model

Two commands cover the benchmark. `gptnt run` plays the interactive suites from a `run.yaml` manifest. `gptnt statics` runs the static suite. This page walks both, then how to read the results.

## The interactive suites

### Declare a run

A `run.yaml` manifest names the suites, how many rooms to play at once, and the roster of models:

```yaml
spec_version: 2
suites:
  - single-pairwise-sync
rooms: 2

players:
  - model: <model-name>
  - model: test_expert

source: local
observability: limited
```

| field           | meaning                                                                                                    |
| --------------- | ---------------------------------------------------------------------------------------------------------- |
| `spec_version`  | manifest version. Must be `2`.                                                                             |
| `suites`        | one or more suite ids from `configs/suites/`.                                                              |
| `rooms`         | how many games to play at once.                                                                            |
| `players`       | the roster. Each entry is a `model` config name, an optional `provider` override, and an optional `count`. |
| `source`        | where the resume check reads completion: `local` (on-disk outputs) or `wandb`.                             |
| `observability` | log verbosity: `full`, `limited`, or `off`.                                                                |

`gptnt list suites` shows the suite ids, and `gptnt list models` the model configs a roster can name.

??? note "Anchors and displays"
    `anchors` names a `best_expert` or `best_defuser` model for matchups that pair against a reference player. `displays` lists X display numbers to spread rooms across on a headless Linux host (see [Installation](../get-started/installation.md)).

### Validate it

```bash
gptnt doctor runs/<name>.yaml
```

This checks the infrastructure and cross-checks the roster against what the suites need, so a missing player surfaces here instead of stalling the run.

### Generate the specs

```bash
gptnt generate runs/<name>.yaml
```

This writes one experiment spec per mission, pairing, and attempt under `output/experiment_specs/<name>/`.

??? question "Why is this separate from running?"
    Generation is offline and deterministic; running spawns the game and spends tokens. Keeping them apart lets you inspect the specs, and lets a run resume by regenerating the same set and skipping what is already done. See [Tracking experiments](../concepts/tracking-experiments.md).

### Play

```bash
gptnt run runs/<name>.yaml
```

`run` gates on `doctor`, spawns the experiment manager, game rooms, and players, submits the specs, and streams progress until the run finishes. Add `-i`/`--interactive` to stream process logs instead of the status table, or `--force` to proceed past doctor warnings.

With a display, the game window opens. Headless, it runs in the background and you watch the logs.

### Read the results

Each experiment is written to a parquet file under `output/experiment_recorder_outputs/`. Build the local database from that directory, then list or browse:

```bash
gptnt build-db <outputs-dir>   # the parquet directory the run reported
gptnt results                  # list the outcomes
gptnt analyse                  # open the Streamlit dashboard
```

For what is written, where, and how a re-run knows what is already done, see [Tracking experiments](../concepts/tracking-experiments.md).

## The static suite

The benchmark also includes one static evaluation, `expert-vqa-no-manual`. It reads the manual without playing the game:

```bash
gptnt statics expert-vqa-no-manual --model <model-name> --throw
```

`--throw` runs the evaluation; without it the command does a dry run. `--limit-instances N` caps the instance count while you test.

??? note "Other statics tasks"
    `gptnt statics` also has tasks like `defuser-vqa-mcq`, `defuser-grounding-som`, and `expert-ocr`. They check a model's vision and reading before you spend compute on interactive play, and are not part of the benchmark. Run `gptnt statics --help` for the full list.
