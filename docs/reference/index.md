---
title: Reference
---

# Reference

Reference pages describe accepted commands, settings, values, states, and runtime contracts. Use
the task pages for an end-to-end procedure and these pages when you need an exact interface.

## Available reference groups

| Interface | Use it to find |
| --------- | -------------- |
| [CLI](cli/index.md){data-preview} | Command selection, arguments, options, outputs, and failure boundaries |
| [Configuration](configuration/index.md){data-preview} | Environment variables, runtime endpoints, game settings, and timeouts |
| [Files and schemas](files/index.md){data-preview} | Manual source inputs and compiled outputs |
| [Python interfaces](python/index.md){data-preview} | Selected player, action, observation, and processor objects |
| [Runtime implementation](runtime/index.md){data-preview} | Process orchestration, services, registry state, heartbeats, and RPC |

The glossary joins this section with the remaining concept and reference slices. Runtime pages are
available because they support the first-run and service-troubleshooting paths.

!!! info "Support boundary"
    CLI, configuration, persisted formats, and selected Python imports can be supported interfaces.
    The runtime section instead describes the current implementation for maintainers. A public
    module name does not by itself make every object inside it a supported interface.

<!-- vale ai-tells.DoubleHyphen = NO -->
[Run the quickstart](../start-here/run-quickstart.md)
[Understand GPTNT](../understand/index.md)
<!-- vale ai-tells.DoubleHyphen = YES -->
