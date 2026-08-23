---
title: Service registry
tags:
  - Runtime
  - Maintainer reference
---

# Service registry

The service registry converts heartbeat data into the experiment manager's view of connected,
ready, available, busy, cleaning, and expired player and game services.

!!! info "Current implementation"
    Registry objects and readiness predicates describe the current matchmaking implementation.
    They are not supported extension interfaces.

## Manifest and state

A `ServiceManifest` pairs the latest `PlayerHeartbeat` or `GameHeartbeat` with one manager-owned
`ServiceState`.

| `ServiceState` | Meaning |
| -------------- | ------- |
| `idle` | The manager can consider the service for matchmaking. |
| `in_experiment` | A running session has assigned the service. |
| `cleanup` | A session is stopping or resetting the service. |
| `not_ready` | The manager cannot assign the service. |

Heartbeat readiness and registry state are separate. The service writes readiness. The experiment
manager changes `ServiceState` as it assigns and releases resources.

## Matchmaking availability

A player appears in `ready_players` only when all these conditions hold:

- The latest heartbeat has `ReadyState.ready`.
- The manifest has `ServiceState.idle`.
- The heartbeat is a `PlayerHeartbeat`.
- The player reports `PlayerState.idle`.

A game appears in `ready_games` only when its heartbeat is ready, its manifest is idle, it is a
`GameHeartbeat`, and it reports `GameState.main_menu`.

| Service | Heartbeat readiness | Registry state | Service-specific state |
| ------- | ------------------- | -------------- | ---------------------- |
| Player | `ready` | `idle` | `PlayerState.idle` |
| Game | `ready` | `idle` | `GameState.main_menu` |

## Heartbeat updates and expiry

The registry scans `heartbeat:*` every two seconds. It validates hashes into player or game
heartbeat models and updates the manifest for each UUID. A new UUID creates an idle manifest.

A heartbeat is expired when its timestamp is at least ten seconds old. The registry removes the
manifest, reads any tombstone and remaining Redis-key diagnostics, then calls the experiment
manager's expiry handler. An expired service that was in an experiment forces its session to stop.

`ObservableServiceRegistry` adds gauges for connected, available, running, and cleaning services.
Those metrics do not affect matchmaking predicates.

The registry readiness tests cover ready/idle players, busy players, main-menu games, and separation
between game and player manifests.

[Experiment manager](experiment-manager.md)
[Heartbeats and RPC](heartbeats-and-rpc.md)
