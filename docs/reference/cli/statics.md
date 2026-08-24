---
title: Static evaluation commands
tags:
  - CLI
  - Results
---

# Static evaluation commands

`gptnt statics` runs fixed evaluation tasks against Hugging Face datasets. Dataset-backed tasks
share one option set and always select a local player profile with `--player`.

## Dataset-backed tasks

| Command | Task-specific input |
| ------- | ------------------- |
| `defuser-grounding-coordinates` | Dataset split `test_coordinates`. |
| `defuser-grounding-som` | Dataset split `test_som`. |
| `defuser-vqa-oe` | Open-ended VQA. |
| `defuser-vqa-mcq` | Multiple-choice VQA. |
| `defuser-state-recognition-vqa-mcq` | `--state-split`: `state-change`, `solved`, or `strikes`. Defaults to `state-change`. |
| `expert-vqa` | Expert VQA with the configured manual input. |
| `expert-vqa-no-manual` | Expert VQA without manual input. This is the explicit static submission target. |
| `expert-ocr` | Expert element OCR. |
| `expert-ocr-with-text` | Requires `--manual-artifact PATH`. |
| `expert-element-grounding` | Expert manual-element grounding. |

The common form is:

```text title="Command syntax"
gptnt statics TASK --player NAME [--provider NAME] [--download] [--throw]
                    [--upload] [--limit-instances N]
                    [--dataset-revision REF]
                    [--allow-thinking | --no-thinking]
                    [--allow-modified-benchmark]
```

| Option | Default and effect |
| ------ | ------------------ |
| `--player` | Required name under `configs/player/`. |
| `--provider` | Optional name under `configs/player/provider/`. |
| `--download` | Downloads the dataset before the run for diagnostic use. |
| `--throw` | Executes predictions and local scoring. Disabled by default. |
| `--upload` | Uploads an evaluation to Weave. Disabled by default. |
| `--limit-instances` | Restricts the loaded instances. |
| `--dataset-revision` | Requests a Hugging Face branch, tag, or commit. |
| `--allow-thinking`, `--no-thinking` | Enables thinking by default for dataset tasks. |
| `--allow-modified-benchmark` | Contributor override that marks outputs as non-submittable. |

## `how-do-you`

```text title="Command syntax"
gptnt statics how-do-you --player NAME [--provider NAME]
                         [--attempts N] [--allow-thinking | --no-thinking]
                         [--output-file-prefix PREFIX]
```

`--attempts` is a positive count and defaults to `1`. Thinking is disabled by default on this
command. It writes a module-to-attempt mapping under `output/how_do_you/`; it has no dataset,
download, throw, upload, or benchmark-integrity option.
