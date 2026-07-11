---
title: Submit your results
---

# Submit your results


A submission is a bundle of your results, pinned so anyone can tell how they were measured: the suites and their revisions, your model's capabilities, and the exact GPTNT commit that produced them. You contribute it to the submissions registry by pull request, and an automated check validates it before merge. Again, we've tried to make this as simple as possible but it's still a process.


## Briefly, how this works

At a high-level, you can add and run your model and have all the results there. Then, you're going to need to package them up and submit them.
The submissions process itself is a pull request to [gptnt/submissions](https://github.com/gptnt/submissions), a different repository we are using to keep track of them all.
The PR gets validated for structure and we will check the results out, and then we'll merge it in. After that, we'll update the leaderboard and see how your model compares to the others. There is also a diagram below that shows the flow of the submission process.

Once your model is added and run, submitting takes five steps:

1. [**Collate**](#collate-into-the-single-duckdb-file){data-preview} your experiment outputs into one DuckDB file.
2. [**Build**](#build-the-submission){data-preview} the submission bundle.
3. [**Fill in**](#update-the-submissionyaml-files){data-preview} each `submission.yaml`.
4. [**Check**](#check-it-before-you-send-it){data-preview} the bundle.
5. [**Open**](#open-the-pull-request){data-preview} the pull request.

## What we expect you to have run

For a submission, we ask that you run the following suites:

- `multi-self-async`
- `multi-self-sync`
- `single-parametric-sync`

and the following statics:

- `expert-vqa-no-manual`




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

As mentioned above, the submission is a bundle of the results, and pinned so that anyone can tell how they were measured.
For each bundle, we automatically extract the information and structure it for you to submit. In the end, it'll look something like this:

```yaml
submissions/
└── <model-name>_{capfp8}/ # (1)!
    ├── <suite-name>@<revision>/ # (2)!
    │   ├── experiments.parquet # (3)!
    │   └── submission.yaml
    └── <static-name>@<revision>/ # (4)!
        ├── metrics.json # (5)!
        └── submission.yaml
```

1. The canonical model name and a hash of the capabilities used for the evaluation. E.g., `claude-sonnet-5_3f2a1b8c`.
2. The name and revision of a suite. E.g., `multi-self-async@1`.
3. An `ExperimentSummary` for every single experiment in the suite. This is _not_ the trajectory data.
4. The name and revision of a static evaluation. E.g., `expert-vqa-no-manual@2`.
5. The aggregated scorer outputs for the static evaluation task.


### Run the command(s)

The simplest way to create it is to run the following command:

```bash
gptnt submission new
```

This will use all the default paths to create a submission bundle for all the suites and statics that were run. If you want to create a submission for a specific static or suite, you can use the `--suite` or `--static` flags to specify which one you want to create a submission for.


## Update the `submission.yaml` file(s)

One thing that we can't do for you is fill in the information for the `submission.yaml` file. We'll do as much as we can automatically, but the rest is up to you.

Once you've generated the submission bundle, go to the directory and fill in your details in each `submission.yaml` file. This is important so that we know who you are, what model you used, and how to contact you if we have questions. The `submission.yaml` file is also where you can add any additional information about your submission that you think is important for us to know. For instance, we use it to track what capabilities your model has, what suite you used, and more.

These files get validated against the schema, so if you don't fill them out correctly, the automated check will fail. Please make sure to read the schema and fill out the files correctly.


## Check it before you send it

```bash
gptnt submission validate <submission-bundle-dir>
```

Once you're ready to go, you can run the validation command to check that everything is in order. This will check that the submission bundle is structured correctly, that the `submission.yaml` files are filled out, and that the results make sense. If the validation passes, you're ready to open the pull request. If it fails, you'll need to fix the issues before you can submit.

!!! note
    We use the same command when we validate the submission too.


## Open the pull request

We have automated the process of opening a pull request for you.

<!-- Fork gptnt/submissions, drop your submissions/<id>/ folder in, and open the PR. Point at the
     repo's README for the exact folder layout. -->

