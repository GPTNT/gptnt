---
title: Run the quickstart
---

# Run the quickstart

The quickstart is a self-contained run that will run the entire benchmark from start to finish, without using any real models. It is designed to verify that the benchmark is installed correctly and that everything is working properly. It's also a good way to get familiar with the benchmark and its workflow.

!!! example "If you want to skip forwards"
    Run these commands from the repository root.

    ```bash title="Run the quickstart"
    gptnt manual compile
    gptnt doctor runs/quickstart.yaml
    gptnt generate runs/quickstart.yaml
    gptnt run runs/quickstart.yaml
    # wait for all the runs to finish and then ctrl-c to stop it
    gptnt build-db output/experiment_recorder_outputs
    gptnt results
    ```

## What is a "run manifest"?

We get into this in more detail [later](../run-and-submit/create-run-manifest.md){data-preview},
but a run manifest is a YAML file that describes the run. It selects the following:

1. The **player roster**, a list of players (models) and their providers (how you access them)
1. The **suites**, each of which is a group of experiments to get the players to run
1. The **runtime capacity**, which is how many players and rooms (KTANE instances) can run at once

The manifest for the quickstart is `runs/quickstart.yaml`.

```yaml title="runs/quickstart.yaml"
--8<-- "runs/quickstart.yaml"
```

## Check the plan with the doctor

Once you've installed and prepared GPTNT, you should be able to run this and it should pass without
any errors.

```bash
gptnt doctor runs/quickstart.yaml
```


!!! tip "What to do if the doctor fails"

    Follow
    [installation](../troubleshooting/installation-and-doctor.md),
    [game](../troubleshooting/game-and-displays.md), or
    [runtime](../troubleshooting/redis-and-runtime-services.md) for solutions to common problems.



## Generate experiment specifications

For GPTNT, we generate explicit JSON files for each mission. These specifications are used
to run each experiment and contains all the information needed to run it, without needing
the manifest or any other configuration.[^manifest-gen] Importantly, the generated specifications
are **the only thing that is used to run the experiments.**

[^manifest-gen]: So yes, the run manifest is an abstraction that generates more things.

```bash
gptnt generate runs/quickstart.yaml
```

!!! tip "Spreading the load across multiple machines"

    If you have multiple machines, you can run `generate` on one machine and then copy some of the
    generated JSON files to other machines to be able to run the same experiments across several
    machines.

    One reason for doing this is that there is a limit to how much you can run on a single machine.
    For example, an older machine might not be able to run 20 independent instances of KTANE at
    once.


After you have run `generate`, you can manually inspect the generated specs under `output/experiment_specs/quickstart/`.

!!! info
    Refer to [`generate` reference](../reference/cli/generate.md) describes output overrides and
    integrity conditions.

## Run the experiments

For all the specs that are remaining in `output/experiment_specs/quickstart/`, we can now run them!


```bash
gptnt run runs/quickstart.yaml
```


The `run` command will do the following:

1. Run the `doctor` check to ensure everything is still in order
1. Start all of the GPTNT services: so that's the experiment manager, the players, and the rooms
1. Submit the specifications to the experiment manager, which will then run them as quickly as
possible
1. Monitor the health of the services

And then, the missions just run until they are all finished.



!!! tip "If you want to see the logs"

    Because there are multiple services running, we do not stream logs to the terminal. Instead, we
    output the logs to `output/logs/run_<run-output-name>/`.

    If you want to see the logs in the terminal—say, when you're debugging a problem—you can use the `-i` flag to stream the logs to the terminal.



!!! warning "There is no progress bar"

    The `run` command does not have a progress bar. It will just run until all the experiments are
    finished. You can check the logs in `output/logs/run_<run-output-name>/` to see what is going
    on.

    Again, a legacy thing that we never really needed. We used W&B for progress tracking and
    Logfire to observe how everything was running, so we did not need a progress bar. If you want
    to see the progress, you can use W&B or Logfire to track it.

    <small>(Fixing this is on the [roadmap](../roadmap.md){data-preview}.)</small>


!!! danger "The services do not stop automatically"

    The `run` command will not stop automatically when all the experiments are finished. You can
    either wait for all the experiments to finish and then ++ctrl+c++ to stop it.

    This is a legacy choice, yes, but we did this so that we could submit more experiment specs to
    the Experiment Manager without needing to restart the services.

    <small>(Fixing this is also on the [roadmap](../roadmap.md){data-preview}.)</small>



## Build the results database

When you perform the `run` command, the experiment manager records the results of every experiment
from each agent's own perspective separately. Towards the start of the run, it will print out the
directory where the results are being recorded. It normally resembles
`output/experiment_recorder_outputs/<timestamp>/`.

Using this, build a DuckDB database that collates all the results into a single queryable database
at `output/experiments.duckdb` by default.

```bash
gptnt build-db <outputs-dir>
```

??? question "Why capture the results from each player separately?"

    Because each player is it's own Python process, we didn't want to transfer all the data to the
    Experiment Manager and then collate it there because it could be a bottleneck. Instead, we just
    have each player write its own results to a Parquet file and we collate them later.


## View the results

```bash
gptnt results
```

!!! success "The result is queryable"
    The command renders a table titled `KTANE experiment outcomes`. The quickstart row can report a
    solved, strikeout, or timeout outcome.

The artefacts now form this sequence:

```text title="Quickstart artefacts"
runs/quickstart.yaml
  → output/experiment_specs/quickstart/*.json
  → output/experiment_recorder_outputs/<timestamp>/experiment-*.parquet
  → output/experiments.duckdb
  → gptnt results
```
