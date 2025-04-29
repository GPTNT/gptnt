import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Thread
from typing import Any, override

from pydantic import TypeAdapter
from structlog import get_logger

from gptnt.common.async_ops import busy_wait_interval
from gptnt.common.paths import Paths
from gptnt.players.base_player import BasePlayer
from gptnt.players.human.views.base_view import BaseView, ChatMessage

paths = Paths()
_log = get_logger()


@dataclass(kw_only=True)
class Controller(BasePlayer):
    """Control the frontend with the backend for the UI app."""

    view: BaseView
    gradio_launch_kwargs: dict[str, Any] = field(default_factory=dict)

    @override
    async def on_startup(self) -> None:
        """Build the layout and launch the gradio server.

        Note:
            - All arguments are passed to `gradio.Interface.launch`.
            - Starts gradio on separate thread to prevent blocking logic thread.
        """
        _log.info("Running gradio app", gradio_kwargs=self.gradio_launch_kwargs)
        gradio_interface = self.view.build_layout(
            handle_send=self.handle_user_message,
            handle_pull=self.poll_and_add_new_messages,
            handle_save_history=self.handle_save_history,
        )

        # Run gradio app on separate thread so we can still use main thread for DS client.
        Thread(
            target=lambda: gradio_interface.launch(**self.gradio_launch_kwargs), daemon=True
        ).start()

        _log.debug("Waiting for gradio to finish")
        event = asyncio.Event()
        _ = await event.wait()

    @override
    async def run_parallel(self) -> None:
        return  # noqa: WPS324

    @override
    async def run_sequential(self) -> None:
        return  # noqa: WPS324

    @override
    async def health_check(self) -> None:
        return  # noqa: WPS324

    @override
    async def connect(self) -> None:
        if hasattr(self, "dialogue_space_client"):
            await self.dialogue_space_client.connect()
            _log.info("Connected to dialogue space client")

    @override
    async def disconnect_from_room(self) -> None:
        """Disconnect from the dialogue space room."""
        await super().disconnect_from_room()
        await self.view.disconnect_view_from_room()
        _log.info("Disconnected from dialogue space client")

    async def poll_and_add_new_messages(self) -> AsyncGenerator[list[ChatMessage], None]:
        """Poll dialogue space while connected and update chat history on new msgs."""
        while True:  # noqa: WPS457
            # TODO: Fix this to end at some point?
            if self.dialogue_space_client.is_connected:
                new_messages = await self.dialogue_space_client.pull_messages()
                chat_messages = [
                    ChatMessage(content=message, role="assistant") for message in new_messages
                ]
                self.view.message_history.extend(chat_messages)
                yield self.view.message_history
                _ = await busy_wait_interval()

    async def handle_user_message(self, message: str) -> tuple[list[ChatMessage], str]:
        """Read user message and add it to chat history."""
        # Don't add empty messages
        message = message.strip()

        if not message:
            return self.view.message_history, ""

        # Update model
        await self.dialogue_space_client.send_message(message)

        # Update view
        self.view.add_user_message(message)
        return self.view.message_history, ""

    def handle_save_history(self, save_path: Path | None = None) -> Path:
        """Dumps message history to log file.

        If provided a path, will save to that directory, otherwise will save to
        storage/outputs/gradio_chats. Returns saved log path.
        """
        _log.info("program closing, dumping logs to file")
        game_timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d_%H-%M-%S")

        if save_path is None:
            paths.gradio_chats.mkdir(parents=True, exist_ok=True)
            save_path = paths.gradio_chats

        log_file = save_path.joinpath(f"{game_timestamp}.json")
        log_messages = TypeAdapter(list[ChatMessage]).dump_json(self.view.message_history)
        _ = log_file.write_bytes(log_messages)

        return log_file
