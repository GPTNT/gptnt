"""The `gptnt run` process-supervision engine: spawn, poll, and tear down the cluster.

Rendering-agnostic — operational events go through `structlog` and the live child-log stream is
decoupled via `ProcessOrchestrator.on_spawn`; all rich rendering lives in `gptnt.cli.run`.
"""

from gptnt.interactive.orchestration.orchestrator import (
    ProcessOrchestrator,
    ProcessStatus,
    TrackedProcess,
    abort_on_shutdown,
    fail_and_terminate,
)
from gptnt.interactive.orchestration.spawn import (
    handle_signals,
    spawn_experiment_manager,
    spawn_players,
    spawn_rooms,
)

__all__ = [
    "ProcessOrchestrator",
    "ProcessStatus",
    "TrackedProcess",
    "abort_on_shutdown",
    "fail_and_terminate",
    "handle_signals",
    "spawn_experiment_manager",
    "spawn_players",
    "spawn_rooms",
]
