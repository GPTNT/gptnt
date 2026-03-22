# How to run the static evaluations

We provide a way to run static evaluations of different models using predefined prompts and expected outputs. This is useful for benchmarking and comparing model performance with less variability than interactive play. This is also a good way to make sure that your model is capable of playing the game before spending/wasting compute on interactive gameplay.

## Entrypoint

Statics are integrated into the main `gptnt` CLI under the `statics` sub-command:

```bash
gptnt statics <task> --model <model> [--throw] [--upload]
```

Run `gptnt statics --help` to see all available tasks. Your main arguments are:

- `task`: The task to evaluate
- `--model`: The model to evaluate, from `configs/model/`
- `--throw`: To actually run the evaluation itself. Without this flag, it will just do a dry run.
- `--upload`: To upload the results to Weave. Without this flag, no metrics are computed.
- `--download`: To download and process the dataset before throwing. By default, this is just False and done during the running, but this helps with checking for dataset issues.
- `--limit-instances`: To limit the number of instances to run for debugging purposes.

For example, to run the defuser grounding coordinates evaluation:

```bash
gptnt statics defuser-grounding-coordinates --model <your-model> --throw --upload --limit-instances 10
```

### High-level of how it works

We have created datasets for each task and uploaded them on Hugging Face. Each dataset has the expected prompts, all the images that are needed, and a bunch of expected outputs. This entrypoint is solely focused on running the evaluations on these datasets, and not their creation. The creation is elsewhere _(TODO: where?)_.

It goes in this order:

1. Load the dataset
2. Run the model on each example, and save the output to disk
3. Compute the metrics and upload them to Weave.

### Tasks

Currently, we have the following tasks:

- `defuser-grounding-coordinates`: Element grounding task on the game visuals with coordinates
- `defuser-grounding-som`: Element grounding task on the game visuals with SoM
- `defuser-vqa-mcq`: VQA task on the game visuals with MCQ format
- `defuser-vqa-oe`: VQA task on the game visuals with (slightly/constrained) open-ended format
- `expert-vqa`: VQA task on the manual
- `expert-ocr`: OCR task on the manual
- `expert-element-grounding`: Element grounding task on the manual

### How to choose your model

Models are chosen using Hydra, since we have the glory of Hydra to help. You can find the model choices in `configs/model/`.

## Caveats about the implementation

There is some hackery to connect the correct scoring mechanisms with the correct tasks that isn't great. We started with a more general thing but as it got unwieldy and we were against the clock, there are some small hacks in place in the scorers.
