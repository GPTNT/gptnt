from pydantic_settings import BaseSettings


class ServiceTimeouts(BaseSettings):
    """Configuration for service timeouts."""

    heartbeat_repeat_interval: float = 3
    """Seconds between heartbeats emitted by each service."""

    heartbeat_check_interval: float = 2
    """Seconds between registry scans for expired service heartbeats."""

    heartbeat_expiration: float = 10
    """Seconds after a heartbeat timestamp before the registry expires the service."""

    tombstone_expiration: float = 120
    """Seconds for which a shutdown tombstone remains in Redis."""

    game_state_interval: float = 2
    """Seconds between game-state polls."""

    get_bomb_state_timeout: float = 10
    """Seconds allowed for one `get_bomb_state` RPC."""

    get_observation_timeout: float = 60
    """Seconds allowed for one `get_frames` RPC."""

    update_metrics_interval: float = 5
    """Seconds between service-metric updates."""

    configure_services_timeout: float = 60
    """Seconds allowed to configure the services assigned to an execution."""

    run_forward_pass_timeout: float = 600
    """Reserved forward-pass timeout in seconds.

    Player RPC currently uses `redis_rpc_timeout` instead.
    """

    redis_rpc_timeout: float = 600
    """Seconds allowed for one Redis RPC response unless a client supplies another timeout."""

    maximum_experiment_duration: float = 12000
    """Seconds allowed for each lights-off, lights-on, or game-over wait."""

    session_state_watcher_interval: float = 1
    """Seconds between session-watcher polls of service state."""

    game_request_timeout: float = 5
    """Seconds allowed for the `stop_game` RPC."""
