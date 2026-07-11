# Run the benchmark

!!! warning "Ensure the dummy models work first"
    This section presumes you have already run the benchmark with the dummy models and have a working setup. If you have not, follow [Get started](../get-started.md){data-preview} first.

This section takes you from a working setup to a set of results you can submit. Add your model, run the benchmark's suites, then package the outcome.
The benchmark runs as a set of suites through two commands:

- **Interactive suites** play the game, driven by a `run.yaml` manifest and `gptnt run`.
- **Static evaluations** (`expert-vqa-no-manual`) evaluate the manual without the game, through `gptnt statics`.

## Where to start

!!! danger
    This entire section focuses on getting you to a set of results you can submit. Therefore, various details are going to be left out. Watch this space for additional details on how to go beyond running the existing set of suites.

The pages follow the order you use them:

1. [Add a new player](add-new-player.md){data-preview} — write and validate a model config.
2. [Run your model](run-your-model.md){data-preview} — declare a run, play the suites, read the results.
3. [Submit your results](../submit-your-results.md){data-preview} — package them and open a pull request.
