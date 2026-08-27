---
title: Start here
hide:
  - toc
---

# Start here

!!! warning "The installation process is not a single step"

    Because we are using the real game and running an asynchonrous real-time benchmark, we can't do
    everything in Python to make installing and running easy. Instead, we control as much as we can and simplify the rest. Once you download the benchmark and get the external services running, then that's it. But getting there might feel tricky.

    The process is broken up across several pages so that it is not overwhelming, and that the options you need to make are incredibly obvious.

    At a high-level, the entire process is:

    1. Download GPTNT
    1. Install Python dependencies and Playwright
    1. Copy and paste the game into the right place
    1. Run Redis and an OpenTelemetry collector
    1. Verify it works with `doctor` command and the quickstart config

    After you have verified it works, then you can just run the benchmark however you want and never do those steps again. The whole process from nothing to something on my Macbook takes 5 minutes and I'm copying and pasting commands the entire time.


1. [Install GPTNT](install.md){data-preview}.
   Download the benchmark, install Python dependencies, and install Playwright-managed Chromium.
1. [Prepare GPTNT](prepare.md){data-preview}.
   Run the `doctor` command to verify that the benchmark is installed correctly and that the game and Redis are running.
2. [Run the quickstart](run-quickstart.md){data-preview}.
   Generate specifications, run the included players, build DuckDB, and inspect an outcome.
3. [Choose the next workflow](choose-next-workflow.md){data-preview}.
   Continue to model integration, a larger run, result inspection, submission, or concepts.

## Recover from setup problems

| Observed problem | Troubleshooting page |
| ---------------- | -------------------- |
| Installation or `doctor` fails | [Installation and doctor](../troubleshooting/installation-and-doctor.md) |
| KTANE or its display fails | [Game and displays](../troubleshooting/game-and-displays.md) |
| Redis or a runtime service fails | [Redis and runtime services](../troubleshooting/redis-and-runtime-services.md) |
