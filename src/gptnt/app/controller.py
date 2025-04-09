import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from threading import Thread
from typing import Any, override

from pydantic import TypeAdapter
from structlog import get_logger

from gptnt.app.views.base_player import BasePlayerView, ChatMessage
from gptnt.common.paths import Paths
from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.players.run import RunPlayerMixin

log = get_logger()

paths = Paths()


class Controller(RunPlayerMixin):
    """Control the frontend with the backend for the UI app."""

    def __init__(
        self,
        *,
        view: BasePlayerView,
        dialogue_space_client: DialogueSpaceClient,
        gradio_launch_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.ds_client = dialogue_space_client
        self.view = view

        self.gradio_launch_kwargs = gradio_launch_kwargs or {}

        self._log = get_logger()

    @override
    async def run(self) -> None:
        """Build the layout and launch the gradio server.

        Note:
            - All arguments are passed to `gradio.Interface.launch`.
            - Starts gradio on separate thread to prevent blocking logic thread.
        """
        self._log = self._log.bind(role=self.view.role)
        self._log.info("Running gradio app", gradio_kwargs=self.gradio_launch_kwargs)

        await self.ds_client.connect()

        gradio_interface = self.view.build_layout(
            handle_send=self.handle_user_message,
            handle_pull=self.poll_and_add_new_messages,
            handle_save_history=self.handle_save_history,
        )

        # Run gradio app on separate thread so we can still use main thread for DS client.
        Thread(
            target=lambda: gradio_interface.launch(**self.gradio_launch_kwargs), daemon=True
        ).start()

        self._log.debug("Waiting for gradio to finish")
        event = asyncio.Event()
        _ = await event.wait()

    async def poll_and_add_new_messages(
        self, poll_interval: float = 0.5
    ) -> AsyncGenerator[list[ChatMessage], None]:
        """Poll dialogue space while connected and update chat history on new msgs."""
        while self.ds_client.is_connected:
            new_messages = await self.ds_client.pull_messages()
            chat_messages = [
                ChatMessage(content=message, role="assistant") for message in new_messages
            ]
            self.view.message_history.extend(chat_messages)
            yield self.view.message_history
            _ = await asyncio.sleep(poll_interval)

    async def handle_user_message(self, message: str) -> tuple[list[ChatMessage], str]:
        """Read user message and add it to chat history."""
        # Don't add empty messages
        message = message.strip()

        if not message:
            return self.view.message_history, ""

        # Update model
        await self.ds_client.send_message(message)

        # Update view
        self.view.add_user_message(message)
        return self.view.message_history, ""

    def handle_save_history(self, save_path: Path | None = None) -> Path:
        """Dumps message history to log file.

        If provided a path, will save to that directory, otherwise will save to
        storage/outputs/gradio_chats. Returns saved log path.
        """
        log.info("program closing, dumping logs to file")
        game_timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d_%H-%M-%S")

        if save_path is None:
            paths.gradio_chats.mkdir(parents=True, exist_ok=True)
            save_path = paths.gradio_chats

        log_file = save_path.joinpath(f"{game_timestamp}.json")
        log_messages = TypeAdapter(list[ChatMessage]).dump_json(self.view.message_history)
        _ = log_file.write_bytes(log_messages)

        return log_file
