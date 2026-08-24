---
title: Runtime implementation
tags:
  - Runtime
  - Maintainer reference
---

# Runtime implementation

These pages trace how `gptnt run` validates work, starts processes, assigns services, exchanges
commands, records progress, and handles failure.

!!! info "Maintainer reference"
    This section describes the current implementation. Its classes, private modules, Redis keys,
    and HTTP routes are not supported extension interfaces unless another reference page says so.

## Trace by operation

| Operation | Page |
| --------- | ---- |
| Validate, prepare, spawn, submit, monitor, and terminate | [Run orchestration](run-orchestration.md) |
| Queue specifications, match services, and run sessions | [Experiment manager](experiment-manager.md) |
| Configure KTANE, observe state, and apply actions | [Game service](game-service.md) |
| Prepare model input, perform calls, communicate, and record | [Player service](player-service.md) |
| Determine readiness, availability, and expiry | [Service registry](service-registry.md) |
| Inspect liveness keys, request channels, and timeouts | [Heartbeats and RPC](heartbeats-and-rpc.md) |
| Write player records, finalise outcomes, and ingest results | [Recording and completion](recording-and-completion.md) |
