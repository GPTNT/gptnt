---
title: Submit your results
---

# Submit your results


A submission is a bundle of your results, pinned so anyone can tell how they were measured: the suites and their revisions, your model's capabilities, and the exact GPTNT commit that produced them. You contribute it to the submissions registry by pull request, and an automated check validates it before merge. We've tried to make this as simple as possible but it's still a process.


## Briefly, how this works

Once your model is added and run, you have all the results sitting on disk. You package them up, check them, and send them as a pull request to [gptnt/submissions](https://github.com/gptnt/submissions), a separate repository we use to track them all. The PR gets validated for structure, we check the results, and we merge it in. After that, your results will join the others on the leaderboard.

Submitting takes four steps:

1. [**Collate**](#collate-into-the-single-duckdb-file){data-preview} your experiment outputs into one DuckDB file.
2. [**Build**](#build-the-submission){data-preview} the submission bundles, filling in who you are.
3. [**Check**](#check-it-before-you-send-it){data-preview} them.
4. [**Submit**](#open-the-pull-request){data-preview} the pull request.


## Before you start

We ask that you run the following suites:

- `multi-self-async`
- `multi-self-sync`
- `single-parametric-sync`

and the following static:

- `expert-vqa-no-manual`

Each model you submit needs a filled `identity` block in its player config (`configs/player/<player-name>.yaml`). This is where the display name, organisation, URL, and open-source flag come from. If you followed the steps to [add a new player](running/add-new-player.md#configuring-the-identity){data-preview}, you already have it. If it's missing, `gptnt submission new` will stop and tells you.

The final step opens a pull request for you, which needs a bit more:

- The `submission` extra, for the git and GitHub plumbing:

    ```bash
    uv sync --all-groups --extra submission
    ```

- A GitHub token, either in the `GITHUB_TOKEN` environment variable or through an authenticated `gh` CLI (`gh auth login`).


## Collate into the single DuckDB file

During the running of the models, each player in each experiment produces their own output file. This means that if we have two players, we have two files for that experiment. If we have ten, we have ten files. To make life easier for analysis and submission, we collate all of the outputs into a single DuckDB file.

To collate your experiment outputs into a single DuckDB file, you can use the following command:

```bash
gptnt build-db <directory-of-experiment-outputs> -o <output-duckdb-file>
```

??? question "Why DuckDB?"
    DuckDB is a lightweight, columnar, database. For storing data like the records from an experiment, it is a good choice because it is fast, easy to use, and can handle large datasets. It's also directly supported by [Polars](https://pola.rs) and [PyArrow](https://arrow.apache.org/docs/python/index.html), which means we can easily read and write in a format that is compatible across the different tools we use. DuckDB is also fast, which is important for building it as fast as possible and using it, without needing to wait forever.

??? question "Do you need to keep the DuckDB _and_ the raw experiment outputs?"
    Not really. Once you have everything in the DuckDB, there isn't really much reason to keep the raw outputs around. However, if you want to just in case, highly recommended.

??? tip "Use more workers for faster processing"
    If you have access to more compute, you can use the `-j` flag to use more workers for the reading and parsing of the parquet files, which can speed up the process significantly.

    If you want to know how long it can take, it mainly depends with the experiments. But here's a rough estimate: with 9000 parquet files across 5050 experiments, it took about 20 minutes to collate them with `-j 126`. But here's an important caveat: most of the time was taken by building the DuckDB itself, which DuckDB handles, so there isn't too much we can do to speed it up (as far as I know, but I might be wrong).




## Build the submission

The submission is a bundle of your results, pinned so anyone can tell how they were measured. We extract and structure everything for you. You get one bundle per model per target (a suite or a static), and they land under `output/submissions/`:

```yaml
submissions/
├── 20260711_claude-sonnet-5_3f2a1b8c_multi-self-async_1/ # (1)!
│   ├── submission.yaml
│   └── experiments.parquet # (2)!
└── 20260711_claude-sonnet-5_3f2a1b8c_expert-vqa-no-manual_9f8e7d6c/ # (3)!
    ├── submission.yaml
    └── metrics.json # (4)!
```

1. The build date, the model's display-name slug, an 8-character hash of the capabilities used, the suite, and its revision.
2. An `ExperimentSummary` for every experiment in the suite. This is _not_ the trajectory data.
3. A bundle for a static evaluation. Same naming, ending in the static's name and the dataset revision it ran against.
4. The aggregated scorer outputs for the static, copied across as-is.

To build them, run:

```bash
gptnt submission new \
  --submitter.name "<name>" \
  --submitter.contact "@<handle>" \
  --submitter.affiliation "<affiliation>" \
```

`--submitter.contact` is your GitHub handle or an email, so we can reach you. There's also an optional `--submitter.affiliation`. This uses the default paths and builds a bundle for every suite and static you ran. To target a specific one, pass `--suite` or `--static`; to build for specific models only, pass `--model`.

Everything else is filled in for you. Your capabilities are read from the results and pinned with a fingerprint, so there is nothing to hand-edit there, and editing them only makes the check fail. The display name, organisation, and the rest come from the `identity` block in the player config, not from anything you type here.

??? tip "Prefer to fill it in by hand?"
    If you leave the submitter flags off, the `submitter` block in each `submission.yaml` is written blank for you to fill in afterward. Rebuilding keeps whatever you've already put there, so you won't lose it.


## Check it before you send it

```bash
gptnt submission validate
```

Once you're ready to go, run the validation command to check that everything is in order. It checks that each bundle is structured and named correctly, that the `submitter` block is filled, that the suite is frozen, and that every mission was run exactly once and ended cleanly. If it passes, you're ready to open the pull request. If it fails, fix the issues it lists before you submit.

A couple of things only warn, and won't block you: a static whose dataset revision wasn't pinned at run time (pin it with `--dataset-revision` when you run statics, for a reproducible submission), and a git tree that had uncommitted changes when the results were produced.

!!! note
    We run this same command when we validate your submission on our end.


## Open the pull request

The last step opens the pull request for you, one per bundle, against [gptnt/submissions](https://github.com/gptnt/submissions). It needs the `submission` extra and GitHub auth from [Before you start](#before-you-start){data-preview}.

Do a dry run first. This clones, branches, and commits locally, and shows you each branch, the files it would stage, and the PR title, without touching GitHub:

```bash
gptnt submission submit --dry-run
```

When it looks right, drop the flag:

```bash
gptnt submission submit
```

If you have push access to the registry it pushes a branch directly; otherwise it forks the repository first and pushes there. Re-running is safe: it updates the branch and the existing pull request rather than opening a new one.

That pull request is your submission. From there we validate it, check the results, and merge it in.
