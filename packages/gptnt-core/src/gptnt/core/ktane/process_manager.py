import os
from dataclasses import dataclass, field

import anyio
import logfire
import structlog
from anyio.abc import Process

from gptnt.core.common.servers import get_available_port
from gptnt.core.ktane.executable import get_executable_path
from gptnt.core.ktane.game_settings import KtaneSettings

logger = structlog.get_logger()


@dataclass(kw_only=True)
class GameProcessManager:
    """Manage KTANE itself."""

    _process: Process | None = field(default=None, init=False)
    _port: int | None = field(default=None, init=False)

    @property
    def port(self) -> int | None:
        """Get the port the game process is running on."""
        return self._port

    @property
    def is_alive(self) -> bool:
        """Check if the game process is alive."""
        return self._process is not None and self._process.returncode is None

    @logfire.instrument("Start game")
    async def start(self) -> int:
        """Start the game process and return the port."""
        if self.is_alive:
            raise RuntimeError("Game process already running")

        # Setup game settings
        ktane_settings = KtaneSettings()
        ktane_settings.create_settings_files()

        # Get port and prepare environment
        self._port = get_available_port()
        env = os.environ.copy()
        env["port"] = str(self._port)

        # Start process
        self._process = await anyio.open_process(
            cwd=get_executable_path().parent, command=[get_executable_path()], env=env
        )
        logger.info("Game process started", port=self._port)
        return self._port

    @logfire.instrument("Terminate game")
    async def terminate(self, *, shutdown_time: float = 5) -> None:
        """Terminate the game process gracefully."""
        if not self._process:
            return

        if self._process.returncode is None:
            logger.info("Terminating game process", port=self._port)
            self._process.terminate()

            # Give it time to shut down gracefully
            with anyio.move_on_after(shutdown_time):
                _ = await self._process.wait()

            # Force kill if still running
            if self._process.returncode is None:
                logger.warning("Force killing game process", port=self._port)
                self._process.kill()
                _ = await self._process.wait()

        self._process = None
        self._port = None

    async def wait(self) -> int:
        """Wait for the process to exit and return the exit code."""
        if not self._process:
            raise RuntimeError("No process to wait for?")
        return await self._process.wait()
