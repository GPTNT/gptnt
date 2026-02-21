import abc
from dataclasses import dataclass
from typing import ClassVar

import logfire
from opentelemetry.metrics import Counter, _Gauge as Gauge

from gptnt.common.async_ops import periodic
from gptnt.common.instrumentation import ObservabilitySettings
from gptnt.services.timeouts import ServiceTimeouts

service_timeouts = ServiceTimeouts()
observability_settings = ObservabilitySettings()


@dataclass(kw_only=True)
class LogfireGauge(abc.ABC):
    """Gauges for Logfire metrics."""

    connected_players_gauge: ClassVar[Gauge] = logfire.metric_gauge(
        "connected_players", description="Number of connected players"
    )
    connected_games_gauge: ClassVar[Gauge] = logfire.metric_gauge(
        "connected_games", description="Number of connected games"
    )

    available_players_gauge: ClassVar[Gauge] = logfire.metric_gauge(
        "available_players", description="Number of available players"
    )
    available_games_gauge: ClassVar[Gauge] = logfire.metric_gauge(
        "available_games", description="Number of available games"
    )

    running_players_gauge: ClassVar[Gauge] = logfire.metric_gauge(
        "running_players", description="Number of running players"
    )
    running_games_gauge: ClassVar[Gauge] = logfire.metric_gauge(
        "running_games", description="Number of running games"
    )

    cleanup_players_gauge: ClassVar[Gauge] = logfire.metric_gauge(
        "cleanup_players", description="Number of players in cleanup state"
    )
    cleanup_games_gauge: ClassVar[Gauge] = logfire.metric_gauge(
        "cleanup_games", description="Number of games in cleanup state"
    )

    available_experiments_gauge: ClassVar[Gauge] = logfire.metric_gauge(
        "remaining_experiments", description="Number of remaining experiments"
    )
    running_experiments_gauge: ClassVar[Gauge] = logfire.metric_gauge(
        "running_experiments", description="Number of running experiments"
    )
    completed_experiments_counter: ClassVar[Counter] = logfire.metric_counter(
        "completed_experiments", description="Number of completed experiments"
    )
    failed_experiments_counter: ClassVar[Counter] = logfire.metric_counter(
        "failed_experiments", description="Number of failed experiments"
    )

    async def metrics_loop(self) -> None:
        """Periodically update the metrics."""
        async for _ in periodic(service_timeouts.update_metrics_interval):
            if observability_settings.enable_metrics:
                self._update_all_metrics()

    @abc.abstractmethod
    def _update_all_metrics(self) -> None:
        """Update all metrics with the current state."""
        raise NotImplementedError
