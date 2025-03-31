import asyncio
from threading import Thread
from typing import Any, override

from gradio import ChatMessage

from gptnt.app.views.base_player import BasePlayerView
from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.players.run import RunPlayerMixin


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

    @override
    async def run(self) -> None:
        """Build the layout and launch the gradio server.

        Note:
            - All arguments are passed to `gradio.Interface.launch`.
            - Starts gradio on separate thread to prevent blocking logic thread.
        """
        await self.ds_client.connect()

        gradio_interface = self.view.build_layout(
            handle_send=self.handle_user_message, handle_pull=self.handle_pull_button
        )

        # Run gradio app on separate thread so we can still use main thread for DS client.
        Thread(
            target=lambda: gradio_interface.launch(**self.gradio_launch_kwargs), daemon=True
        ).start()

        event = asyncio.Event()
        _ = await event.wait()

    async def handle_pull_button(self, history: list[ChatMessage]) -> list[ChatMessage]:
        """Logic for 'pull messages' button."""
        # Get messages from model
        new_messages = await self.ds_client.pull_messages()

        # Append each new message to chat history via view
        for msg in new_messages:
            history = self.view.add_external_message(msg, history)

        return history

    async def handle_user_message(
        self, message: str, history: list[ChatMessage]
    ) -> tuple[list[ChatMessage], str]:
        """Handle user message send."""
        # Don't add empty messages
        message = message.strip()

        if not message:
            return history, ""

        # Update model
        await self.ds_client.send_message(message)

        # Update view
        self.view.add_user_message(message, history)
        return history, ""
