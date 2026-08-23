---
title: CLI reference
tags:
  - CLI
---

# CLI reference

GPTNT registers commands with Cyclopts under the `gptnt` entry point. These pages cover the
commands used by the first-run and runtime path.

| Command group | Reference |
| ------------- | --------- |
| Validate configuration, infrastructure, players, and run plans | [`doctor`](doctor.md) |
| Generate persisted experiment specifications | [`generate`](generate.md) |
| Start, submit, monitor, or forcibly stop interactive work | [`run`, `submit`, and `kill`](run.md) |

Model onboarding, manuals, result analysis, static evaluations, submission, and maintenance stay
with their existing task pages until their connected reference pages are integrated.

## Command order for an interactive run

```bash
gptnt doctor runs/<name>.yaml
gptnt generate runs/<name>.yaml
gptnt run runs/<name>.yaml
```

`run` does not call `generate`. The separation lets you inspect and retain the exact specifications
before any game or player process starts.

<!-- vale ai-tells.DoubleHyphen = NO -->
[Run the quickstart](../../start-here/run-quickstart.md){ .md-button .md-button--primary }
[Open runtime reference](../runtime/index.md){ .md-button }
<!-- vale ai-tells.DoubleHyphen = YES -->
