# Run the benchmark

!!! warning "Ensure the dummy models work first"
    This section presumes you have already run the benchmark with the dummy models and have a working setup. If you have not, follow [Get started](../get-started/installation.md) first.

This section takes you from a working setup to a set of results you can submit. Add your model, run the benchmark's suites, then package the outcome.
The benchmark runs as a set of **suites** through two commands:

- **Interactive suites** play the game, driven by a `run.yaml` manifest and `gptnt run`.
- **A static suite** (`expert-vqa-no-manual`) evaluates the manual without the game, through `gptnt statics`.

## Where to start

!!! danger
    This entire section focuses on getting you to a set of results you can submit. Therefore, various details are going to be left out. If you have "why" and "how" questions, you'll want to explore the various [concepts](../concepts/) and the [internals](../internals/).

The pages follow the order you use them:

1. [Add your model](add-your-model.md) — write and validate a model config.
2. [Run your model](run-your-model.md) — declare a run, play the suites, read the results.
3. [Submit your results](submit-your-results.md) — package them and open a pull request.
