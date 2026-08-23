---
title: Redis and runtime service troubleshooting
tags:
  - Runtime
  - Configuration
---

# Redis and runtime service troubleshooting

Check the endpoint first, then service readiness, heartbeat state, the RPC operation, and the
process log. These checks separate transport failures from a child process or operation that
exceeded its timeout.

!!! warning "Protect the default Redis endpoint"
    The Compose service listens on `localhost:6379` without authentication. Do not expose it to an
    untrusted network. Use `REDIS_DSN` for a Redis deployment that requires another host,
    transport, database, or credentials.

## Redis is unreachable

Start the included service:

```bash
docker compose up -d
gptnt doctor runs/<name>.yaml
```

Doctor sends Redis `PING` to the configured `REDIS_DSN`. A failed row means no successful response
was received. Check that the endpoint, authentication, and network route match every service
process. Starting the development telemetry profile does not change Redis:

```bash
COMPOSE_PROFILES=dev docker compose up -d
```

## Redis authentication fails

The included Compose service has no password. A separately managed Redis service can require a
credential in its DSN. Set one `REDIS_DSN` in the environment inherited by the CLI and child
processes. Do not place a credential in a tracked manifest or example.

## The experiment manager does not become ready

`gptnt run` starts the manager and polls
`http://<GPTNT_EM_HOST>:<GPTNT_EM_PORT>/health` every 0.5 seconds. It stops the cluster when the
manager exits or does not respond successfully within 60 seconds.

Inspect `experiment_manager.log` in the run log directory printed by the pre-flight summary. Check
Redis first because the manager lifespan opens Redis before serving the runtime registry.

## The experiment-manager port is occupied

Doctor treats a responding GPTNT health endpoint as an existing manager and reports the port as
occupied. It also reports a listener that does not provide the expected response. Determine which
run owns the process before stopping it.

Use [`gptnt kill`](../reference/cli/run.md#kill) only for a leftover GPTNT cluster. Use
`GPTNT_EM_HOST` and `GPTNT_EM_PORT` only when every client and service should use another endpoint.

## A service never becomes ready

The experiment manager can match only:

- a player with a ready heartbeat, idle registry state, and `PlayerState.idle`;
- a game with a ready heartbeat, idle registry state, and `GameState.main_menu`.

Inspect the service log for configuration or startup failure. Then compare its heartbeat and
registry predicates in the [service registry reference](../reference/runtime/service-registry.md).

## A heartbeat expires

Services refresh heartbeat hashes every three seconds; the registry treats them as expired after
ten seconds. On graceful shutdown, a tombstone remains for 120 seconds.

Expiry diagnostics record the last sequence, uptime, PID, hostname, heartbeat key state and TTL,
and any tombstone. No tombstone normally indicates unexpected disappearance. A partial hash
indicates that Redis still held some fields when the registry diagnosed expiry.

An expired service assigned to an experiment forces that session to stop. Use the PID and hostname
to select the corresponding process log before restarting the run.

## An RPC call times out

!!! failure "The subscriber did not return before the operation limit"
    Do not increase the timeout before checking Redis reachability, the service heartbeat, registry
    readiness, and the corresponding process log. The subscriber may be absent or the child
    process may have failed.

The general Redis RPC timeout is 600 seconds. Bomb state uses 10 seconds, observations use 60
seconds, and short game-control requests use 5 seconds. A player model pass has a separate
600-second limit.

The channel identifies the target:

```text
game:<uuid>:commands:<command>
player:<uuid>:commands:<command>
```

## A child process exits

The run monitor marks a non-zero child exit as failed, logs the process name, PID, exit code, and
log path, then terminates the remaining cluster. Open the referenced log rather than starting
another cluster over the same failure.

With `gptnt run ... -i`, the terminal streams the same prefixed output while retaining the files.

## Specification submission fails

`run` submits only after the manager, rooms, and players start. A failed `POST /add-specs`
terminates the cluster. HTTP 409 means an existing queued or running attempt name is already bound
to different specification content. Use one consistent generated directory and remove conflicting
work only after identifying which run owns it.

## Telemetry is unreachable

The doctor telemetry check is optional and reports a warning. It is not a Redis or experiment
manager failure. Use `COMPOSE_PROFILES=dev` when the collector endpoint should remain available but
discard exported telemetry.

[Heartbeats and RPC](../reference/runtime/heartbeats-and-rpc.md){ .md-button }
[Understand runtime services](../understand/runtime-services.md){ .md-button }
