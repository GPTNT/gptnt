from dataclasses import dataclass
from typing import ClassVar

import logfire
from opentelemetry.metrics import _Gauge as Gauge


@dataclass(kw_only=True)
class LogfireGauge:
    """Gauges for Logfire metrics."""

    connected_rooms: ClassVar[Gauge] = logfire.metric_gauge(
        "connected_rooms", description="Number of connected rooms"
    )
    connected_players: ClassVar[Gauge] = logfire.metric_gauge(
        "connected_players", description="Number of connected players"
    )
    connected_games: ClassVar[Gauge] = logfire.metric_gauge(
        "connected_games", description="Number of connected games"
    )

    available_rooms: ClassVar[Gauge] = logfire.metric_gauge(
        "available_rooms", description="Number of available rooms"
    )
    available_players: ClassVar[Gauge] = logfire.metric_gauge(
        "available_players", description="Number of available players"
    )
    available_games: ClassVar[Gauge] = logfire.metric_gauge(
        "available_games", description="Number of available games"
    )

    running_rooms: ClassVar[Gauge] = logfire.metric_gauge(
        "running_rooms", description="Number of running rooms"
    )
    running_players: ClassVar[Gauge] = logfire.metric_gauge(
        "running_players", description="Number of running players"
    )
    running_games: ClassVar[Gauge] = logfire.metric_gauge(
        "running_games", description="Number of running games"
    )

    available_experiments: ClassVar[Gauge] = logfire.metric_gauge(
        "remaining_experiments", description="Number of remaining experiments"
    )
    running_experiments: ClassVar[Gauge] = logfire.metric_gauge(
        "running_experiments", description="Number of running experiments"
    )
