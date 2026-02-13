from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from gptnt.services.timeouts import ServiceTimeouts

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from faststream.redis import RedisBroker

timeouts = ServiceTimeouts()
logger = structlog.get_logger()


@dataclass(kw_only=True)
class BaseRPCService[CommandKeyT](ABC):
    """Base class for services that handle RPC commands via Redis.

    Subclasses must:
    - Define a `command_channel` property that returns the base channel name
    - Define a `commands` dict mapping command names to handler functions
    - Have a `broker` attribute of type RedisBroker
    """

    broker: RedisBroker
    commands: dict[CommandKeyT, Callable[..., Any | Awaitable[Any]]] = field(init=False)

    @property
    @abstractmethod
    def command_channel(self) -> str:
        """Get the base command channel for this service.

        Example: "player:{uuid}:commands" or "game:{uuid}:commands"
        """
        ...

    def register_subscribers(self) -> None:
        """Register all command subscribers with the broker.

        This method should be called during service initialization (e.g., in __post_init__). It
        iterates through all commands and registers them as Redis subscribers.
        """
        for command_name, command_func in self.commands.items():
            channel_name = f"{self.command_channel}:{command_name}"
            logger.debug(
                "Registering RPC command",
                channel_name=channel_name,
                command=command_name,
                service_type=self.__class__.__name__,
            )
            _ = self.broker.subscriber(channel_name)(command_func)


@dataclass(kw_only=True)
class BaseRPCClient(ABC):
    """Base class for clients that make RPC calls to services via Redis.

    Subclasses must:
    - Define a `command_channel` property that returns the base channel name
    - Have a `broker` attribute of type RedisBroker
    """

    broker: RedisBroker

    @property
    @abstractmethod
    def command_channel(self) -> str:
        """Get the base command channel for the target service.

        Example: "player:{uuid}:commands" or "game:{uuid}:commands"
        """
        ...

    def _get_channel(self, command: str) -> str:
        """Get the full Redis channel name for a given command.

        Args:
            command: The command name (e.g., "get_state", "configure_game")

        Returns:
            Full channel name (e.g., "player:uuid:commands:get_state")
        """
        return f"{self.command_channel}:{command}"

    async def _send_command(
        self,
        command: str,
        payload: dict[str, Any] | None = None,
        timeout: float = timeouts.redis_rpc_timeout,  # noqa: ASYNC109
    ) -> Any:
        """Send a command via Redis RPC and wait for response.

        Args:
            command: The command name to execute
            payload: Optional payload dict to send with the command
            timeout: Optional timeout in seconds (defaults to redis_rpc_timeout)

        Returns:
            The decoded response from the service

        Note:
            The broker is assumed to be already started and managed by FastStream.
        """
        channel = self._get_channel(command)
        response = await self.broker.request(payload or {}, channel=channel, timeout=timeout)
        return await response.decode()
