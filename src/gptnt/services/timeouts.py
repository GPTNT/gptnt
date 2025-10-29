from pydantic_settings import BaseSettings


class ServiceTimeouts(BaseSettings):
    """Configuration for service timeouts."""

    heartbeat_repeat_interval: float = 3
    """Interval for sending heartbeat messages."""

    heartbeat_check_interval: float = 2
    """Interval for checking heartbeat messages."""

    heartbeat_expiration: float = 10
    """Expiration time for heartbeat messages sent."""

    game_state_interval: float = 2
    """Interval for requesting the game state."""

    get_bomb_state_timeout: float = 10
    """Timeout for getting the bomb state in a request."""

    get_observation_timeout: float = 60
    """Timeout for getting an observation from the game."""

    update_metrics_interval: float = 5
    """Interval for updating service metrics."""

    configure_services_timeout: float = 60
    """Timeout for configuring services for an experiment."""

    run_forward_pass_timeout: float = 600
    """Timeout for running a forward pass for a player."""

    maximum_experiment_duration: float = 6000
    """Maximum duration for an experiment before it is forcibly stopped."""

    session_state_watcher_interval: float = 1
    """Interval for the session state watcher to check service states."""
