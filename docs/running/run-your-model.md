# Run your model

To run the benchmark, there are two commands that you will use: `gptnt run` and `gptnt statics`. The first command runs the interactive experiments, while the second command runs the static experiments.

## Interactive experiments

An interactive run goes through five steps:

1. [**Declare**](#declare-a-run){data-preview} a `run.yaml` manifest.
2. [**Validate**](#validate-it){data-preview} it with `doctor`.
3. [**Generate**](#generate-the-specs){data-preview} the experiment specs.
4. [**Play**](#play){data-preview} the suites.
5. [**Read**](#read-the-results){data-preview} the results.

### Declare a run

A `run.yaml` manifest names the suites, how many rooms to play at once, and the roster of players. The easiest way to start is to copy one of the templates in `runs/`, rename it, and adjust the suites and players.

- `runs/_template.yaml` is the commented starting point for a custom run.
- `runs/quickstart.yaml` is the smallest smoke-test style run with the test players.
- `runs/headline.yaml` runs the benchmark headline suites reported in the leaderboard: self play on the multi-module sync and async suites.
- `runs/all-suites.yaml` runs the full suite set used in the paper.

For example, a custom run might look like:

```yaml
spec_version: 2
suites:
  - single-pairwise-sync
  - multi-self-sync
rooms: 2

players:
  - player: qwen3-5-27b
    provider: vllm_box1 # (1)!
    count: 2
  - player: claude-sonnet-4-6 # (2)!
    count: 2

source: local
observability: limited
```

1. Qwen 3.5 27B with a provider override from `configs/player/provider/vllm_box1.yaml`.
2. Claude 4.6 with the default provider (Anthropic).

#### Basic fields

These are the fields needed for a typical run:

| Field | Meaning | Default |
| ----- | ------- | ------- |
| `spec_version` | Manifest version. Must be `2`. | `2` |
| `suites` | One or more suite ids from `configs/suites/`. Run `gptnt list suites` to see the available ids. | Required |
| `rooms` | How many games to play at once. | Required |
| `players` | The roster. Each entry is a `player` config name, an optional `provider` override, and an optional `count`. Run `gptnt list players` to see the available player configs. | Required |
| `source` | Where GPTNT checks for completed experiments when resuming a run:<br>`local` checks the on-disk output files, while `wandb` checks W&B runs. | `local` |
| `observability` | Log verbosity: `full`, `limited`, or `off`. | `limited` |

!!! important "Set player capacity with `count`"
    Set the number of instances to spawn on each `players` entry using `count`. Every room needs two player instances: one will be the Defuser and one the Expert. To use `n` rooms concurrently, the `count` values across the roster must add up to at least `2 × n`. For example, `rooms: 4` requires a total `count` of at least eight. If you omit `count`, that roster entry contributes only one instance.

    Self-play is a special case: the same model fills both roles, so set `count: 2` or higher on every participating player.

#### Advanced fields

Most runs can use the defaults for these fields. Configure them when you need explicit display placement, anchored matchups, or repeated attempts.

##### Displays

`displays` spreads game rooms round-robin across X displays on a headless Linux host (see [rendering the game](../get-started.md#rendering-the-game-display-vs-headless){data-preview}). Use one display number per GPU to spread rooms across GPUs, for example `displays: [0, 1]`. Omit it to inherit the ambient `$DISPLAY`.

```yaml hl_lines="6"
spec_version: 2
suites:
  - single-pairwise-sync
rooms: 2

displays: [0, 1]
```

##### Anchors

`anchors` names a `best_expert` or `best_defuser` player for matchups that pair candidates against a fixed reference player. For example, a suite that uses a fixed expert can read that expert from `anchors.best_expert`, while the other players in `players` are the candidates being evaluated.

```yaml hl_lines="12 13"
spec_version: 2
suites:
  - single-parametric-sync
rooms: 2

players:
  - player: qwen3-5-27b
    count: 2
  - player: gemini-3-flash-preview
    count: 2

anchors:
  best_expert: gemini-3-flash-preview
```

Any anchor referenced by the selected suites must also appear in `players`, otherwise `doctor` fails the run manifest check.

##### Attempts

`attempts_per_mission` controls how many independent attempts to run per mission and pairing. It defaults to `1`, and is originally set by the suite generator. You can override this on run level if you wish to average multiple runs or derive a pass@k. Note that the leaderboard will also always report a pass@1 as per the original setting.

```yaml hl_lines="6"
spec_version: 2
suites:
  - single-pairwise-sync
rooms: 2

attempts_per_mission: 3
```

### Validate it

```bash
gptnt doctor runs/<name>.yaml
```

This checks the infrastructure and cross-checks the roster against what the suites need, so a missing player surfaces here instead of stalling the run.

### Generate the specs

```bash
gptnt generate runs/<name>.yaml
```

This writes one experiment spec per mission, pairing, and attempt under `output/experiment_specs/<name>/`. If `attempts_per_mission` is greater than `1`, each mission/pairing is repeated that many times as independent attempts.

??? question "Why is this separate from running?"
    Generation is offline and deterministic; running spawns the game and spends tokens. Keeping them apart lets you inspect the specs, and lets a run resume by regenerating the same set and skipping what is already done.
    <!-- See [Tracking experiments](../concepts/tracking-experiments.md). -->

### Play

```bash
gptnt run runs/<name>.yaml
```

`run` verifies everything is setup with the `doctor`, spawns the experiment manager, game rooms, and players, submits the specs, and streams progress until the run finishes. Add `-i`/`--interactive` to stream process logs instead of the status table, or `--force` to proceed past doctor warnings.

With a display, the game window opens. Headless, it runs in the background and you watch the logs.

### Read the results

Each experiment is written to a parquet file under `output/experiment_recorder_outputs/`. Build the local database from that directory, then list or browse:

```bash
gptnt build-db <outputs-dir> # (1)!
gptnt results # (2)!
gptnt analyse # (3)!
```

1. Reads from the parquet output directory.
2. Lists the outcomes.
3. Opens the Streamlit dashboard.

!!! tip "Where do I find `<outputs-dir>`?"
    `gptnt run` prints the parquet output directory when it records results. It is usually a timestamped directory under `output/experiment_recorder_outputs/`.

<!-- For what is written, where, and how a re-run knows what is already done, see [Tracking experiments](../concepts/tracking-experiments.md). -->

## The static evaluation

The benchmark also includes one static evaluation, `expert-vqa-no-manual`. It reads the manual without playing the game:

```bash
gptnt statics expert-vqa-no-manual --model <model-name> --throw
```

`--throw` runs the evaluation; without it the command does a dry run. `--limit-instances N` caps the instance count while you test.

??? note "Other statics tasks"
    `gptnt statics` also has tasks like `defuser-vqa-mcq`, `defuser-grounding-som`, and `expert-ocr`. They check a model's vision and reading before you spend compute on interactive play, and are not part of the benchmark. Run `gptnt statics --help` for the full list.
