---
title: CLI reference
tags:
  - CLI
---

# CLI reference

GPTNT registers commands with Cyclopts under the `gptnt` entry point. These pages cover setup,
execution, results, static evaluations, maintenance, and result submission.

| Command group | Reference |
| ------------- | --------- |
| Validate configuration, infrastructure, players, and run plans | [`doctor`](doctor.md) |
| Generate persisted experiment specifications | [`generate`](generate.md) |
| Start, submit, monitor, or forcibly stop interactive work | [`run`, `submit`, and `kill`](run.md) |
| Create and inspect model configuration | [Model and configuration commands](model-and-configuration.md) |
| Download and compile manuals | [Manual commands](manuals.md) |
| Inspect completion and maintain interactive outputs | [Interactive and maintenance commands](interactive-and-maintenance.md) |
| Build and query result data | [Results and analysis commands](results-and-analysis.md) |
| Run dataset-backed evaluations | [Static evaluation commands](statics.md) |
| Build, validate, and submit result bundles | [Submission commands](submission.md) |

## Command order for an interactive run

```bash title="Run the interactive command sequence"
gptnt doctor runs/<name>.yaml
gptnt generate runs/<name>.yaml
gptnt run runs/<name>.yaml
```

`run` does not call `generate`. The separation lets you inspect and retain the exact specifications
before any game or player process starts.

<!-- vale ai-tells.DoubleHyphen = NO -->
[Run the quickstart](../../start-here/run-quickstart.md)
[Open runtime reference](../runtime/index.md)
<!-- vale ai-tells.DoubleHyphen = YES -->
